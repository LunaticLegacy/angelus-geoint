# Angelus 插件系统 — Swarm 执行分解规格（历史规划 + 实现状态）

> **状态：历史规划文档，不等于当前实现。** 本文是插件系统最初按 AgentSwarm 拆分的执行计划（S1–S11）。
> 实际落地的代码已大幅偏离：多个计划产出（`angelus/plugin_paths.py`、`plugins.json`、`bridge_*`、
> checksum、`angelus plugin *` CLI、`plugins/example-tool/`）**从未存在**。
> **当前实现的唯一权威是代码 + §0 现状校正表 + `docs/security.md` / `docs/plugin-api.md`。**
> 阅读 §4/§5/附录时，务必先看 §0，不要把计划中的文件名当成仓库中的真实文件。

---

## 0. 现状校正（唯一权威）

| 单元 | 计划产出（原文） | 实际实现 | 证据（file:line / 结论） |
|---|---|---|---|
| S1 契约 | `docs/plugin-api.md`、`docs/decisions.md` | 两份文档均存在；decisions.md 已加「现状注记」。真实 manifest 校验在 `manifest.py`，不是附录 A 的 schema。 | `manifest.py:132-135`（10 个允许顶层字段 + 未知字段拒绝）、`:189-214`（`_permissions` 无 action 枚举）、`:158-165`（`frontend` 键）、`:294-296`（panels） |
| S2 目录/注册表 | `angelus/plugin_paths.py`、`plugin_manifest.py`、`plugin_registry.py`、`plugins.json` | **文件名全部不存在**。真实实现是 `PluginStore` + `manifest.py`；注册表是 `registry.json`（不是 `plugins.json`）。 | `store.py:37`（`plugin_root = ANGELUS_PLUGIN_DIR or state_root/plugins`）、`:38/:42/:43/:44`（package / legacy packages / data / registry.json）、`store.py:84`（`_write` 原子替换） |
| S3 管理器 | `angelus/plugins/manager.py`、`base.py`（`AngelusPlugin` 基类） | **目录 `angelus/plugins/` 不存在**。真实实现是 `angelus/modules/plugin_module/manager.py`；无 `AngelusPlugin` 基类，插件是提供 `setup`/`teardown` 的模块（`PluginEntrypoint` Protocol）。命名空间是单段下划线名，非点分。 | `manager.py:41-60`（PluginEntrypoint）、`:566`（`_load`）、`:580`（`module_name = f"angelus_plugins_{manifest.name.replace('-','_')}"`）、`:594`（`exec_module`） |
| S4 工具接入 | `angelus/plugins/bridge_tools.py` | **不存在**。工具接入内建在 `manager.py`：`_publish` 把贡献登记进 `ToolRegistry`，命名 `plugin.<name>.<id>`。 | `manager.py:607`（`_publish`）、`:621-625`（`provider_id`/category/tool 命名）、`:645-660`（`_PluginProvider`） |
| S5 钩子接入 | `angelus/plugins/bridge_hooks.py`、`HOOK_EVENTS` 白名单 | **不存在**。仓库无任何 hooks 事件注册机制。 | 全仓库无 `register_hook` / `HOOK_EVENTS` |
| S6 路由/静态 | `angelus/plugins/bridge_routes.py`、`/plugins/<name>/api/*` 插件 APIRouter | 静态白名单路由与 `GET /api/plugins` **存在**；但插件自注册 APIRouter（`register_route`）**不存在**。 | `api/plugins.py:262`（`GET /plugins/{name}/static/{asset:path}`）、`:50`（`GET /api/plugins`）、`:215`（panel invoke）、`manager.py:409`（`static_asset` 白名单） |
| S7 连接器接入 | `angelus/plugins/bridge_connectors.py`、`register_connector` | **不存在**。插件不能注册 connector provider。 | 无 `register_connector`；`models.py` 无此方法 |
| S8 前端机制 | `frontend/static/plugins.js` + `window.Angelus` 桥 + **CSP 调整** | `plugins.js` 与 `window.Angelus` 桥**存在**（含 surface 过滤与 panel invoke）；**CSP 调整不存在**（仓库无 `Content-Security-Policy` 头）；桌面设置页未实现。 | `frontend/static/plugins.js:499-500`（`window.Angelus`）、`:14`（registerPanel/registerCommand/registerSettings）、`:511`（`GET /api/plugins`）、`:304`（surface 过滤）、`:351`（panel invoke）；由 `app.js:22`、`main.js:11` 引入 |
| S9 CLI 分发 | `angelus plugin list|install|...` | **未实现**。`angelus/cli.py` 无任何 plugin 子命令。 | `angelus/cli.py` 全文无 `plugin` 匹配 |
| S10 安全/校验 | `angelus/plugins/security.py`、sha256 checksum 校验 | **文件不存在、checksum 校验不存在**。真实权限边界是 confirm / grant / ToolPolicy 三道门禁，不是独立“S10 校验函数”。`docs/security.md` 存在（已按实现重写）。 | 无 `security.py`、无 `checksum`；门禁见 `api/plugins.py:102-103`、`manager.py:271-273`、`tool_policy.py:62-83`；详见 `docs/security.md` |
| S11 测试/文档/示例 | `test_plugin_api.py`、`test_plugin_registry.py`、`plugins/example-tool/` | 仅 `tests/test_plugin_manager.py`、`tests/test_plugin_docs.py` 存在；`docs/plugin-guide.md` 存在；**`example-tool/` 不存在**，真实插件为 `angelus-deepseek-balance-v0.1.0`、`async-download`、`pofp-ctf`。 | `dir tests\*plugin*` → 两个文件；`dir plugins` → 三个真实包 |

**从未落地汇总**（勿在任何文档中当作既有资产引用）：`angelus/plugin_paths.py`、`angelus/plugin_manifest.py`、
`angelus/plugin_registry.py`、`angelus/plugins/`（含 `manager.py`/`base.py`）、`bridge_tools.py`、
`bridge_hooks.py`、`bridge_routes.py`、`bridge_connectors.py`、`security.py`、`plugins.json`、
`checksum` 校验、`angelus plugin <verb>` CLI 子命令、`plugins/example-tool/`。

---

## 1. 目标（历史）

把插件系统从“一张计划”拆成可由 AgentSwarm 并行/串行调度的最小工作单元。每个单元满足：
唯一 recipient、objective 可独立执行、expected_artifacts 可机械核验、验收内容即 TaskReport 检查单。
（该目标描述的是**规划方法**，与实现状态无关，见 §0。）

## 2. 决策门（历史默认值）

4 个决策点的原始默认值如下。**实际实现已与 D2/D4 偏离**，权威校正见 `docs/decisions.md` 的现状注记：

| # | 决策点 | 规划默认值 | 现状 |
|---|---|---|---|
| D1 | 插件加载模型 | 同进程 import，命名空间 `angelus_plugins.<name>` | 同进程 import 成立；命名空间实为 `angelus_plugins_<name>`（`manager.py:580`）；子进程隔离未实现。 |
| D2 | 插件放置 | `<app_data>/plugins`，与 `workspace/` 并列 | 实为 `state_root/plugins`，可被 `ANGELUS_PLUGIN_DIR` 覆盖（`store.py:37`、`core.py:50-53`）；单插件数据是 `<home>/data/<id>`（`manager.py:597`），非 `<plugin_dir>/<name>/data`。 |
| D3 | 桌面设置页 | 本期不纳入，仅 `/api/plugins` + 前端机制 | 后端 + 前端桥成立（`api/plugins.py:50`、`plugins.js`）；**CSP 自域放行未实现**；桌面设置页未实现。 |
| D4 | 示例插件 | 网络搜索工具，`register_tool` + `register_hook` | 二者均**不存在**；真实运行时方法是 `register_tool_provider`/`register_context_provider`/`register_ui_action`/`setting`（`models.py:372-418`）。`example-tool/` 不存在。 |

## 3. Swarm 拓扑（历史设计，仍可参考）

### 3.1 角色（recipient）

| 角色 | 规划单元 |
|------|----------|
| `coordinator` | S0 决策门、合并 |
| `spec` | S1 契约 |
| `registry` | S2 目录 + 注册表 |
| `runtime-core` | S3 PluginManager 核心 |
| `runtime-tools` | S4 工具接入 |
| `runtime-hooks` | S5 钩子接入（**未实现**） |
| `runtime-routes` | S6 路由/静态挂载 |
| `runtime-connectors` | S7 连接器接入（**未实现**） |
| `frontend` | S8 前端机制 |
| `cli` | S9 分发与 CLI（**未实现**） |
| `security` | S10 安全权限（**checksum 未实现**） |
| `qa` | S11 测试/文档/示例 |

### 3.2 执行图（AgentSwarm edges，历史）

```
coordinator ──► spec(S1) ──► registry(S2) ──► runtime-core(S3)
                                                  │ (split)
             runtime-tools(S4) ◄─┘ runtime-hooks(S5) ◄─┘ runtime-routes(S6) ◄─┘ runtime-connectors(S7) ◄─┘
                                                  │ (gather → split)
             frontend(S8) ◄─┘ cli(S9) ◄─┘ security(S10) ◄─┘
                                                  │ (gather)
             qa(S11) ◄─┘
             coordinator ◄─┘ (merge, 总验收)
```

`coordinator→spec→registry→runtime-core`；`runtime-core→{tools,hooks,routes,connectors}`（split）；
`{tools,hooks,routes,connectors}→{frontend,cli,security}`（gather 后 split）；`{frontend,cli,security}→qa`；`qa→coordinator`。

### 3.3 TaskAssignment 映射规则（历史）

每个单元 S* 实例化为 `TaskAssignment(task_id="S3", recipient="runtime-core", reply_to="coordinator",
objective=<§4>, handoff=<§4>, expected_artifacts=<§4>)`。

## 4. 单元分解（历史 objective / handoff / artifacts）

> 以下 objective 是**规划原文**，其中的文件名多为计划而非现实。落地情况一律以 §0 为准。

### S1 — 契约 · recipient=`spec`
- **规划**：盘点扩展点，撰写 `docs/plugin-api.md`（manifest v1 契约、权限枚举、版本策略）与 `docs/decisions.md`。
- **现状**：两文档存在；但真实 manifest 契约与附录 A 不同（`manifest.py:132-135`），权限 `action` 无枚举（`manifest.py:189-214`）。

### S2 — 目录与注册表 · recipient=`registry`
- **规划**：`angelus/plugin_paths.py` + `plugins.json` 原子写注册表。
- **现状**：名为 `store.py` 的 `PluginStore` + `registry.json`；`plugin_paths.py`/`plugins.json` 不存在。

### S3 — PluginManager 核心 · recipient=`runtime-core`
- **规划**：`angelus/plugins/manager.py` + `base.py`（`AngelusPlugin` 基类 + `PluginRuntime`）。
- **现状**：实现在 `angelus/modules/plugin_module/manager.py`；`angelus/plugins/` 与 `base.py` 不存在；
  `PluginRuntime` 是 dataclass（`models.py:347`），方法见 `models.py:372-418`。

### S4 — 工具接入 · recipient=`runtime-tools`
- **规划**：`angelus/plugins/bridge_tools.py`，工具名 `plugin.<name>.<tool>`。
- **现状**：无 `bridge_tools.py`；工具命名确为 `plugin.<name>.<id>`，由 `manager.py:621-625` 内建完成。

### S5 — 钩子接入 · recipient=`runtime-hooks`
- **规划**：`bridge_hooks.py` 接 agent 事件总线，事件白名单。
- **现状**：**未实现**。无 hooks 机制、无 `HOOK_EVENTS`、无 `bridge_hooks.py`。

### S6 — 路由与静态挂载 · recipient=`runtime-routes`
- **规划**：`/plugins/<name>/static/*` 白名单 + `/plugins/<name>/api/*` 插件路由 + `GET /api/plugins`。
- **现状**：静态白名单与 `GET /api/plugins` 存在（`api/plugins.py:262`、`:50`、`manager.py:409`）；
  插件自注册 APIRouter（`/api/*`）与 `bridge_routes.py` **未实现**。

### S7 — 连接器接入 · recipient=`runtime-connectors`
- **规划**：`bridge_connectors.py` + `register_connector`。
- **现状**：**未实现**。

### S8 — 前端机制 · recipient=`frontend`
- **规划**：`plugins.js` + `window.Angelus` 桥 + 调整 CSP 自域。
- **现状**：`plugins.js` 与 `window.Angelus` 桥存在（`plugins.js:499-500`，含 surface 过滤 `:304`）；
  **CSP 调整未实现**；桌面设置页未实现。

### S9 — CLI 分发 · recipient=`cli`
- **规划**：`angelus plugin list|install|uninstall|enable|disable`。
- **现状**：**未实现**（`angelus/cli.py` 无 plugin 子命令）。

### S10 — 安全权限 · recipient=`security`
- **规划**：权限校验 + sha256 checksum + `docs/security.md`。
- **现状**：`docs/security.md` 存在且已按实现重写；无独立权限校验函数、**无 checksum 校验**；
  真实门禁为 confirm / grant / ToolPolicy（`api/plugins.py:102-103`、`manager.py:271-273`、`tool_policy.py:62-83`）。

### S11 — 测试、文档与示例 · recipient=`qa`
- **规划**：`test_plugin_manager.py`、`test_plugin_api.py`、`test_plugin_registry.py`、`docs/plugin-guide.md`、`plugins/example-tool/`。
- **现状**：仅 `tests/test_plugin_manager.py` 与 `tests/test_plugin_docs.py` 存在；`docs/plugin-guide.md` 存在；
  `test_plugin_api.py`/`test_plugin_registry.py`/`example-tool/` **不存在**。

## 5. 验收内容（规划检查单 — 多数未达成）

原文 §5 的 S1–S11 检查单是规划期验收标准。按 §0 现状：S1/S2/S3/S4/S6/S8/S11 **部分落地**；
S5（钩子）、S7（连接器）、S9（CLI）、S10 的 checksum 校验 **完全未实现**。
任何下游引用前，以 §0 现状表与 `docs/security.md` 为准，不要照抄原文检查单当作“已完成”。

## 6. 风险与注意事项（历史）

- **子模块边界**：llmfetcher 为 submodule；桥接只允许在 angelus 侧（S4/S5 已不再按原计划新增 `bridge_*` 文件）。
- **依赖约束**：requirements 无 jsonschema；manifest 校验手写（`manifest.py`）。
- **原子写**：注册表写入为 `.tmp` + `replace()`（`store.py:84` 起），但文件是 `registry.json` 而非 `plugins.json`。
- **无 Rust 工具链**：不涉及 src-tauri 改动（D3 已排除桌面设置页）。

## 附录（计划契约 — 除 E 外均未落地）

> **附录 A/B/C/D 是计划期的契约草案，未按此实现。** 真实 manifest 契约见 `docs/plugin-api.md` 与
> `angelus/modules/plugin_module/manifest.py`；真实运行时 API 见 `models.py:347-418`；真实 REST 契约见
> `api/plugins.py`（`GET /api/plugins` 起于 `:50`）。以下内容仅作历史记录保留。

### A. plugin manifest v1（计划 JSON Schema — 未实现）
计划字段含 `entry_type`、`dependencies`、`checksum`、`permissions[].action` 枚举等；
真实允许的顶层字段只有 10 个（`manifest.py:132-135`），无 `entry_type`/`dependencies`/`checksum`，权限 `action` 无枚举（`manifest.py:189-214`）。

### B. plugins.json 注册表 v1（计划 — 未实现）
真实注册表是 `registry.json`（`store.py:44`），字段见 `store.py` 的 `PluginRecord`（`models.py:244`）。

### C. AngelusPlugin / PluginRuntime 契约（计划 — 未实现）
真实 `PluginRuntime`（`models.py:347`）字段：`plugin`、`settings`、`state_path`、`contributions`、
`context_contributions`、`ui_actions`；方法：`register_tool_provider`、`register_context_provider`、
`register_ui_action`、`setting`（`models.py:372-418`）。**无** `register_tool`/`register_route`/`register_hook`/`register_connector`。
插件无 `AngelusPlugin` 基类；入口是提供 `setup(runtime)`/`teardown()` 的模块（`manager.py:41-60`）。

### D. /api/plugins REST 契约（计划 — 实际不同）
真实端点：`GET /api/plugins`（`api/plugins.py:50`）、`GET /api/plugins/status`（`:63`）、
`POST /api/plugins/rescan`（`:76`）、`POST /api/plugins/discovered/{name}/register`（`:90`）、
`POST /api/plugins/{id}/load`（`:110`）、`POST /api/plugins/{id}/unload`（`:134`）、
`GET /api/plugins/{id}/settings`（`:176`）、`POST /api/plugins/{id}/panels/{panel_id}/invoke`（`:215`）、
`GET /plugins/{name}/static/{asset:path}`（`:262`）。**无 enable/disable 路由、无 `/plugins/<name>/api/*` 挂载。**

### E. Swarm 对接（task_bus 映射，历史设计）
| 单元 | task_id | recipient | 依赖 |
|------|---------|-----------|------|
| S1 | S1 | spec | §2 决策默认值 |
| S2 | S2 | registry | S1 |
| S3 | S3 | runtime-core | S1+S2 |
| S4 | S4 | runtime-tools | S3 |
| S5 | S5 | runtime-hooks | S3 |
| S6 | S6 | runtime-routes | S3 |
| S7 | S7 | runtime-connectors | S3 |
| S8 | S8 | frontend | S4–S7 |
| S9 | S9 | cli | S4–S7 |
| S10 | S10 | security | S4–S7 |
| S11 | S11 | qa | S8–S10 |
