# Angelus 插件系统 — 安全模型（现状）

> **状态**：本文只描述**当前代码**。基线：`angelus/modules/plugin_module/{manifest,manager,models,store}.py`
> 与 `angelus/api/plugins.py`。插件**没有**独立的安全模块。
>
> **重要更正**：本文件旧版声称的 `angelus/plugins/security.py`、`check_permission()` 9 动作枚举、
> `checksum` / `verify_plugin_integrity()`、`bridge_tools|hooks|routes|connectors`、`HOOK_EVENTS`
> 事件白名单、`angelus.plugins.security` 审计日志，在代码里**都不存在**，逐条对照见 §8。
> §9 的 v2 子进程隔离是**路线图**，同样未实现。
>
> MCP server 的凭据存储与项目边界不在本文范围（属 MCP 模块），本文不重复描述。

## 0. 一句话结论

当前插件安全模型是：**安装即信任 + 显式确认 + 声明/授予记录 + manifest 校验收窄面 +
插件工具按会话 `ToolPolicy` 授权**。它不是沙箱——插件代码与宿主同进程、同特权（§1）。

---

## 1. 信任边界：插件代码 = 宿主特权

`PluginManager._load()` 直接在宿主进程里执行插件模块：

- `spec.loader.exec_module(module)`（`manager.py:594`）
- 构造 `PluginRuntime(...)`（`manager.py:596`），随后 `entrypoint.setup(runtime)`（`manager.py:598`）

因此 `setup()` 里的 `import os; os.system(...)`、任意文件读写、任意网络请求，与宿主自身能力等价。
**没有运行时隔离、没有系统调用过滤、没有权限降级。**

结论：安全模型的前提是"用户确认后才加载可信插件"；插件作者被视为可信。

---

## 2. 三道真实存在的门

### 2.1 显式确认 `confirm=true`

`PluginConfirmation`（`api/plugins.py:23-33`）只有两个字段：`confirm: bool = False`、
`grant_permissions: bool = False`。三个生命周期端点都要求 `confirm` 为真，否则 422：

| 端点 | 检查位置 | 拒绝文案 |
|------|----------|----------|
| `POST /api/plugins/discovered/{name}/register` | `api/plugins.py:102-103` | `plugin registration requires confirm=true` |
| `POST /api/plugins/{plugin_id}/load` | `api/plugins.py:122-123` | `plugin load requires confirm=true` |
| `POST /api/plugins/{plugin_id}/unload` | `api/plugins.py:146-147` | `plugin unload requires confirm=true` |

`register` 只做发现、校验并落记录，**不 import 包代码**（`manager.py:226-247`）；真正执行代码的是 `load`。
所以"注册"是安全的静态动作，"加载"才是代码执行边界。

### 2.2 声明 → 授予（知情同意记录）

**声明**：`manifest.permissions` 是 `{action, scope}` 对象数组，由 `_permissions()` 校验
（`manifest.py:189-214`）：`action` 非空且 ≤80 字符、`scope` 非空且 ≤500 字符，否则
`permission action and scope must be bounded strings`（`manifest.py:207-208`）。

> **没有动作枚举。** 任意 `action` 字符串只要长度合法就被接受；代码里不存在
> `shell` / `network` / `fs.read` / `event.subscribe` 这类白名单常量。

**授予**：`PluginManager.load(plugin_id, *, grant_permissions)`（`manager.py:249`）：

- `missing = tuple(p for p in manifest.permissions if p not in record.permissions_granted)`（`manager.py:271`）；
- `missing` 非空且 `grant_permissions=False` → `ValueError("plugin permissions require explicit confirmation")`
  （`manager.py:272-273`），API 层转成 **409**（`api/plugins.py:126-127`）；
- 授权则把 `missing` 追加进 `record.permissions_granted` 并持久化（`manager.py:274`）。

**启动恢复**：`restore_enabled()` 用 `grant_permissions=False` 逐个加载（`manager.py:208-224`）；
声明了新权限的插件不会被静默授权，而是加载失败并被跳过（`manager.py:221-223`）。

**可观测**：`GET /api/plugins/status` 投影同时给出 `permissions_requested` 与
`permissions_granted`（`manager.py:821-822`）。

**关键事实**：`permissions_granted` **不参与任何运行时能力判断**。全仓库没有函数在调用插件代码前
比对它；它只用于"声明了新的权限时必须再确认一次"和状态展示。把它当作访问控制执行点会误判本系统。

### 2.3 manifest 校验收窄攻击面

`_decode_manifest()`（`manifest.py:120-186`）是最强的**结构性**防线：

| 约束 | 位置 | 效果 |
|------|------|------|
| 顶层只允许 10 个键：`name, display_name, version, api_version, kind, entry, description, permissions, frontend, settings_schema` | `manifest.py:132-135` | 未知键 → `unknown manifest fields: ...`；写 `checksum` / `handler` / `script` 直接报错 |
| `api_version` 必须为 `"1"` | `manifest.py:143-145` | 老 API 清单不能混入 |
| `entry` 必须是 Python 模块名 `[A-Za-z_][A-Za-z0-9_]*`，且只有 `tool` 可声明 | `manifest.py:146-151` | 不能写路径；`ui` / `theme_pack` 不能有入口 |
| `frontend` 只允许 `assets` / `settings` / `themes` / `panels` | `manifest.py:158-161` | 没有 `commands`、没有 `scripts` |
| 声明了面板时 `kind` 必须是 `tool` | `manifest.py:163-165` | `frontend panels require a tool plugin entry` |
| 面板对象只允许 `id, title, description, action, submit_label, fields, surface, slot` | `manifest.py:294-296` | 不允许 `handler` / `script` / `html` / `url` |
| 面板字段 key 形状像凭据时必须 `sensitive: true`，且只能 `string` + `format: password` + 无 `default` | `manifest.py:354-359` | 密钥不会以"默认值"形式落进 manifest |
| `settings_schema` 的 key 不允许凭据形状 | `manifest.py:417-418` | `settings key is invalid or credential-shaped` |

---

## 3. 运行期唯一的会话级门禁：插件工具走 `ToolPolicy`

插件工具不是"因为声明了权限所以能调"，而是"因为这个会话的 `ToolPolicy` 放行才会出现"：

1. **加载时固定命名空间**：provider id 为 `plugin.<name>.<index>`，工具 id 为
   `plugin.<name>.<tool_id>`，类别为 `plugin.<name>.<category_id>`（`manager.py:625-635`）。
2. **命名空间强制**：materialize 后若存在不带 `plugin.<name>.` 前缀的工具 →
   `RuntimeError("plugin emitted a Tool outside its namespace")`（`manager.py:698-700`）。
3. **会话执行时判定**：`ToolPolicy.allows(category_id, tool_id)` 要求类别在 `categories` 里**且**
   工具 id 在 `tools` 里（`tool_policy.py:62-83`）；legacy `plugin` 类别仍在
   `tool_policy.py:81-82` 被兼容。
4. **默认不放行**：`DEFAULT_RUN_PROFILE["tool_permissions"]` 不列任何插件类别/工具
   （`profile_store.py:41-51`，注释原文 "Plugin grants are never listed"）。
   ⇒ 新会话里插件工具默认不可调用，需要用户在会话 profile 里显式打开。
5. **卸载清理**：`unload` 删除所有会话 profile 中以 `plugin.<plugin_id>.` 开头的类别与工具键
   （`api/plugins.py:150-169`），避免残留授权在插件重新出现时"复活"；
   前缀常量 `PLUGIN_PERMISSION_PREFIX = "plugin."`（`profile_store.py:73`）。

这是当前**唯一按会话生效**的插件能力门禁，粒度为"该会话能否调用该插件工具"。

---

## 4. 密钥不会进入插件（结构上如此）

- `PluginRuntime` 只暴露 4 个方法：`register_tool_provider`（`models.py:372`）、
  `register_context_provider`（`models.py:383`）、`register_ui_action`（`models.py:387`）、
  `setting`（`models.py:404`）。没有 connector、HTTP client、密钥读取入口。
- **插件设置只能是非密钥标量**：`settings_schema` 的 key 若含
  `api_key / apikey / token / password / secret / credential`（`_SENSITIVE`，`manifest.py:26`）
  直接被拒（`manifest.py:417-418`）。所以设置里存不下密钥。
- **面板字段允许敏感输入**，但强制 `string` + `format: password` + 不允许 `default`
  （`manifest.py:358-359`）；值只存在于单次 `invoke` 请求（`api/plugins.py:215-247`），不落盘。
- 宿主没有把 connector 密钥注入插件的代码路径；插件工具 handler 只拿到本轮工具参数。
- **反向边界（必须明示）**：插件自己的 `state_path` = `<plugin_root>/data/<plugin id>`
  （`manager.py:596-597`）归插件所有，插件可以往里写任何东西，包括它自己收集的密钥；
  宿主不做内容审计。

---

## 5. 静态资源：白名单 + `resolve()` 越界检查

`GET /plugins/{name}/static/{asset:path}`（`api/plugins.py:262-282`，`include_in_schema=False`）。
`PluginManager.static_asset()`（`manager.py:441-453`）逐项检查：

1. 插件必须**已加载**（`self._loaded.get(name)`），否则返回 `None` → 404
   （`api/plugins.py:278-279`）；
2. `asset` 必须与 manifest 里声明的 `assets` 字符串**完全一致**（`manager.py:450-451`）；
3. `root = package_path.resolve()`；`target = (root / asset).resolve()`；必须满足
   `target.is_file()` 且 `root in target.parents`（`manager.py:452-453`）——
   `..`、绝对路径、符号链接逃逸在 `resolve()` 后都会落到 root 之外而被拒；
4. `assets` 自身在校验期也不许绝对路径或含 `..` 的段（`manifest.py:214-236`）。

---

## 6. 面板调用：只走一个端点，先校验再执行

唯一入口 `POST /api/plugins/{plugin_id}/panels/{panel_id}/invoke`（`api/plugins.py:215-247`）。
`PluginManager.invoke_panel()`（`manager.py:397-439`）的执行顺序：

1. 记录存在且插件已加载，否则 `KeyError` → 404 `active plugin panel not found`
   （`api/plugins.py:240-241`）；
2. `panel_id` 必须是 manifest 声明过的 id，否则 `KeyError`（`manager.py:426-428`）；
3. 对应 `ui_action` 必须已注册，否则 `RuntimeError("plugin panel action is not registered")`
   （`manager.py:429-431`）；
4. 字段值经 `_validate_fields(panel.fields, values, defaults=True)` 校验（`manager.py:432`）：
   `required`、类型、`enum`、`minimum` / `maximum` 不合规 → `ValueError` → **422**
   （`api/plugins.py:242-243`）；
5. handler 异常被包成 `RuntimeError("plugin panel action failed: <Type>: <msg>")`
   （`manager.py:433-436`），不把 traceback 泄漏给浏览器；
6. 返回值必须是 `PluginUiActionResult`（`title` / `content` / `tone` 纯文本），否则 422
   （`manager.py:437-439`）；
7. 状态投影不含 `action` id 与 handler（`_panel_json()`，`manager.py:852-870`），
   浏览器拿不到可直接调用的动作名。

---

## 7. 现状边界一览

| 攻击面 | 现状 | 依据 |
|--------|------|------|
| 插件代码越权 | **无隔离**；插件与宿主同权 | `manager.py:594-598` |
| 未确认就执行代码 | 有门：`confirm=true` | `api/plugins.py:102-103,122-123` |
| 声明新权限不确认 | 有门：`grant_permissions=true`，否则 409 | `manager.py:271-274` |
| 已授予权限被运行时强制 | **没有**；grant 只是记录 | 全仓库无 `check_permission`（§8） |
| 插件工具被任意会话调用 | 默认不能；需会话 profile 显式授权 | `profile_store.py:41-51`、`tool_policy.py:62-83` |
| 读 connector 密钥 | 结构上无入口 | `models.py:372-418` |
| 设置/面板默认值藏密钥 | 有门 | `manifest.py:358-359,417-418` |
| 静态资源穿越 | 有门 | `manager.py:441-453` |
| 面板字段类型/必填/枚举 | 有门（422） | `manager.py:432` |
| 安装后被篡改 | **无检测**；没有 checksum | §8 |
| 拒绝事件审计 | **无**；只有 legacy 布局告警日志 | `manager.py:556-560` |

---

## 8. 旧版声称、但代码里不存在的实现

| 旧版说法 | 真实情况 |
|----------|----------|
| `angelus/plugins/security.py`（权限门禁 + checksum + 审计） | 不存在；`angelus/` 下没有 `plugins` 包（只有 `api` / `geoint` / `modules`） |
| `check_permission(plugin_id, action, scope, registry)`、`require_permission` | 全仓库无此符号 |
| 9 动作枚举：`shell` / `network` / `fs.read` / `fs.write` / `env` / `http` / `connector.read` / `connector.write` / `event.subscribe` | 不存在；`action` 是自由字符串（≤80 字符，`manifest.py:207`） |
| `plugins.json[].permissions_granted` 是 `"action:scope"` 字符串数组 | 是 `PluginPermission(action, scope)` 对象元组（`models.py:19-30`、`models.py:250-268`） |
| `manifest.checksum`、`verify_plugin_integrity()`、`compute_plugin_integrity()`、registry 交叉校验 | 不存在；写 `checksum` 会触发 `unknown manifest fields`（`manifest.py:132-135`） |
| `bridge_tools.py` / `bridge_hooks.py` / `bridge_routes.py` / `bridge_connectors.py` | 不存在；工具接入点是 `ToolRegistry` + `manager._publish()`（`manager.py:609-654`） |
| `HOOK_EVENTS` 事件白名单、`register_hook()`、`event.subscribe` 门禁、钩子异常隔离 | 不存在；`PluginRuntime` 无事件订阅面（`models.py:372-418`） |
| `register_connector()`、`connector.read` 授权、`redact_connector()`、`_public_connector` 脱敏 | 不存在 |
| `angelus.plugins.security` logger、`SECURITY <EVENT> k=v` 审计日志、`PERMISSION_DENIED` / `INTEGRITY_DENIED` 等事件 | 不存在；插件模块唯一的日志是 `_LOGGER.warning` 的 legacy `packages/` 布局告警（`manager.py:556-560`） |
| CLI `angelus plugin install / list / enable / disable / uninstall`、`-y` 跳过确认 | 不存在；生命周期只经 HTTP API（`api/plugins.py`）或 Python API |
| `plugins.json` 注册表 | 不存在；注册表是 `<plugin_root>/registry.json`（`{"schema_version": 1, "plugins": [...]}`） |
| `install` / `enable` 流程生成权限确认清单 | 没有 `install`；确认发生在 `POST .../load` 的 `grant_permissions` |
| CSP 只放开同源插件路径 | 未在插件代码中实现；插件资源走上面的普通静态路由 |

---

## 9. v2 子进程隔离（**未实现**，路线图）

§8 的更正意味着：v1 没有"门禁下沉到 IPC 边界"这回事可供继承。下面是**设计意图**，不是现状：

| 维度 | v2 目标 |
|------|---------|
| 进程模型 | 每插件一个子进程或受限 worker 池，宿主与插件只经 JSON-RPC / IPC 通道 |
| 命名空间 | 子进程 `sys.path` 只含插件目录与受控依赖 |
| 权限执行 | 能力请求变成 IPC 消息，宿主判定后再代理执行；届时 `permissions_granted` 才真正成为执行判据 |
| 系统隔离 | POSIX 上降权用户 + seccomp-bpf + rlimit（CPU / 内存 / 文件数 / 进程数）；文件访问经宿主代理或只读 bind-mount |
| 网络 | 子进程经宿主代理出网，按 manifest 声明的 scope 限流 |
| 密钥 | 密钥永不进入子进程，只在宿主侧单次请求中注入 |
| 生命周期 | watchdog 覆盖崩溃/超时/资源超限，插件 OOM 不拖垮宿主 |
| 兼容 | `manifest` 契约与 `api_version` 不变，新增 v2 加载器 |

落地之前，任何"我们已经有权限门禁 / 校验和 / 审计日志"的说法都不成立。

---

## 10. 验证本文档

| 断言类 | 测试 |
|--------|------|
| 生命周期、权限确认、面板调用 | `tests/test_plugin_manager.py` |
| 文档与实现不漂移 | `tests/test_plugin_docs.py` |
| 安全模块（check_permission / checksum / 审计） | **没有** `tests/test_security.py`——模块本身不存在 |
