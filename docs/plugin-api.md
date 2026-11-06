# Angelus 插件系统 API 契约（v1）

> 状态：v1，与 `angelus/modules/plugin_module/` 的实现逐条对齐
> （事实源：`manifest.py` / `models.py` / `manager.py` / `store.py`）。
> 本文只描述**代码中已存在**的契约。历史版本声称过的 hooks / routes / connectors /
> 安装 CLI / 权限运行时门从未实现，统一在 §5 列出，请勿按那套「半协议」开发。
> 面向插件作者的教程见 [plugin-guide.md](plugin-guide.md)，声明式面板见
> [plugin-panel-manifest.md](plugin-panel-manifest.md)。

---

## 1. 事实基线

### 1.1 模块布局

```text
angelus/modules/plugin_module/
├── __init__.py   # 16 个公开导出（§1.2）
├── manifest.py   # load_manifest() / ManifestError：纯 JSON 解码，不导入插件代码
├── models.py     # PluginManifest / PluginRuntime / 贡献类型 / UI 结果 dataclass
├── store.py      # PluginStore：package/ 扫描根、data/ 私有目录、registry.json 原子写
└── manager.py    # PluginManager：发现、注册、加载、发布、卸载、设置、面板调用
```

插件的 Python 代码**只能**从 `angelus.modules.plugin_module` 导入 §1.2 的 16 个名字。
仓库中不存在 `angelus/plugins/` 包，也不存在 `angelus.plugin_manifest` 模块；
`manifest.py` 与 `manager.py` 都位于 `angelus/modules/plugin_module/` 之下。

### 1.2 公开导出（16）

| 名字 | 定义位置 | 用途 |
|------|----------|------|
| `PluginManager` | `manager.py` | 进程内插件生命周期的唯一权威：发现、注册、加载、卸载、设置、面板调用 |
| `PluginManifest` | `models.py` | 校验通过的清单（不可变 dataclass） |
| `PluginPermission` | `models.py` | `(action, scope)` 请求项，不做枚举校验（§3） |
| `PluginRecord` | `models.py` | 本地注册记录：`id` / `name` / `package_path` / `enabled` / `permissions_granted` / `settings` |
| `PluginRuntime` | `models.py` | 传给 `setup()` 的受限宿主对象（§4.2） |
| `PluginSettingField` | `models.py` | `settings_schema` 的一条字段（宿主渲染表单用） |
| `PluginSettingValue` | `models.py` | 一条已保存的标量设置 `(key, value)` |
| `PluginTheme` | `models.py` | 主题包的一个 CSS 变体 `(id, title, asset, mode)` |
| `PluginToolCategory` | `models.py` | 插件自有工具类别 `(id, title, description)` |
| `PluginToolContribution` | `models.py` | 一次工具贡献 `(provider, categories, definitions)` |
| `PluginToolDefinition` | `models.py` | 插件本地工具定义 `(id, category_id, title, description, roles)` |
| `PluginContextContribution` | `models.py` | Composer 上下文源贡献 `(provider, roles)` |
| `PluginPanel` | `models.py` | 声明式面板 `(id, title, description, action, submit_label, fields)` |
| `PluginPanelField` | `models.py` | 面板字段（一次性输入，可标记 `sensitive`） |
| `PluginUiActionRequest` | `models.py` | 传给 action 的已校验输入，`request.value(key, default)` 取值 |
| `PluginUiActionResult` | `models.py` | action 返回值 `(title, content, tone)`，`tone` ∈ `info`/`success`/`error` |

`__all__` 就是上表 16 项；`manifest.py` 另公开 `load_manifest()` 与 `ManifestError`。

---

## 2. manifest v1 契约

`manifest.json` 位于插件包目录根部。`load_manifest(package_path)` 只读
`<package_path>/manifest.json`，**不导入任何插件代码**；任何不合规都抛
`ManifestError`（`ValueError` 的子类），`PluginManager.rescan()` 把它转成该包的
`state: "error"` 条目，`error` 字段就是错误原文。

### 2.1 顶层字段

`_decode_manifest()` 的允许集合只有 10 个键；其余一律拒绝，报
`unknown manifest fields: <按字母序逗号分隔>`。

| 字段 | 类型 | 必填 | 代码约束 | 失败信息 |
|------|------|------|----------|----------|
| `name` | string | ✅ | 非空，≤64 字符，且匹配 `^[a-z][a-z0-9_-]{1,63}$`（最短 2 字符） | `name must match ^[a-z][a-z0-9_-]{1,63}$` |
| `display_name` | string | – | ≤120 字符；缺省取 `name` | `display_name must be a string of at most 120 characters` |
| `version` | string | ✅ | ≤32 字符，且匹配 `^\d+\.\d+\.\d+$` | `version must be semantic x.y.z` |
| `api_version` | string | ✅ | ≤16 字符，且必须等于 `"1"` | `api_version must be '1'` |
| `kind` | string | – | `tool` / `ui` / `theme_pack`，缺省 `tool` | `kind must be tool, ui, or theme_pack` |
| `entry` | string | 仅 `kind=tool` | 必须是 Python 模块名 `[A-Za-z_][A-Za-z0-9_]*`；其它 kind 出现即报错 | `tool plugin entry must be a Python module name` / `only tool plugins may declare entry` |
| `description` | string | – | ≤2000 字符 | `description must be a string of at most 2000 characters` |
| `permissions` | array | – | `{action, scope}` 对象数组（§3） | `permissions must be an array` |
| `frontend` | object | – | 只允许 `assets` / `settings` / `themes` / `panels`（§2.2） | `unknown frontend fields: ...` |
| `settings_schema` | array | – | 标量长期配置（§2.3） | `settings_schema must be an array` |

#### 2.1.1 完整示例（`kind: "tool"`）

```json
{
  "name": "hello-tool",
  "display_name": "Hello Tool",
  "version": "0.1.0",
  "api_version": "1",
  "kind": "tool",
  "entry": "main",
  "description": "示例：注册一个工具，并提供声明式面板与长期配置。",
  "permissions": [
    {"action": "fs.read", "scope": "knowledge/**"}
  ],
  "frontend": {
    "assets": ["panel.css"],
    "settings": true,
    "panels": [
      {
        "id": "lookup",
        "title": "知识查询",
        "description": "在本地知识库中查找片段。",
        "action": "lookup",
        "submit_label": "查询",
        "fields": [
          {
            "key": "query",
            "type": "string",
            "title": "关键词",
            "required": true,
            "placeholder": "例如 heap overflow"
          },
          {
            "key": "limit",
            "type": "integer",
            "title": "结果数",
            "default": 10,
            "minimum": 1,
            "maximum": 100
          }
        ]
      }
    ]
  },
  "settings_schema": [
    {
      "key": "root_dir",
      "type": "string",
      "title": "知识库目录",
      "description": "留空时使用插件私有目录。",
      "format": "path",
      "placeholder": "绝对路径",
      "default": ""
    }
  ]
}
```

### 2.2 `frontend`

`frontend` 必须是对象，键只允许 `assets`、`settings`、`themes`、`panels`。

| 键 | 类型 | 约束 |
|----|------|------|
| `assets` | string[] | 唯一；每项匹配 `^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$`；不能以 `/` 开头；不能含 `..` 路径段。是 `GET /plugins/<name>/static/<asset>` 的唯一白名单（§6.1） |
| `settings` | boolean | 缺省 `false`；`settings_schema` 非空时必须为 `true` |
| `themes` | object[] | 仅 `kind: "theme_pack"` 可声明（§2.4） |
| `panels` | object[] | 仅 `kind: "tool"` 可声明；必须是面板**对象**数组（§2.5） |

错误原文：`frontend.assets must be an array`、`frontend asset must be a safe relative path`、
`frontend assets must be unique`、`frontend.settings must be boolean`、
`frontend panels require a tool plugin entry`。

### 2.3 `settings_schema`（长期保存的非敏感配置）

- 非空时必须同时声明 `frontend.settings: true`，否则 `settings_schema requires frontend.settings=true`。
- 每项允许的属性只有：`key`、`type`、`title`、`description`、`required`、`default`、
  `enum`、`minimum`、`maximum`、`format`、`placeholder`；未知属性报
  `settings_schema contains an unknown field property`。
- `key` 匹配 `^[a-z][a-z0-9_-]{0,119}$`，且不得是凭据形状
  （`api_key`/`apikey`/`token`/`password`/`secret`/`credential` 任一词出现在
  `key` 中，判定前把 `-` 换成 `_` 并转小写），否则
  `settings key is invalid or credential-shaped`。密钥请走面板的 `sensitive` 字段（§2.5）。
- `type` ∈ `string` / `integer` / `number` / `boolean`（`settings type is invalid`）。
- `default` 与 `enum` 的每个值都必须与 `type` 精确匹配（`bool` 不算 `integer`）：
  `settings default does not match <key> type`、`settings enum must contain values of the declared type`。
- `minimum`/`maximum` 只允许用于 `integer`/`number`，且 `minimum <= maximum`：
  `settings minimum is numeric only`、`settings maximum is numeric only`、
  `settings minimum must not exceed maximum`。
- `format` ∈ `uri` / `path` / `textarea`，且只能用于 `string`：
  `settings format supports only string uri, path, or textarea`。
- `key` 在整份 schema 内唯一（`settings keys must be unique`）。
- `title` ≤120、`description` ≤1000、`placeholder` ≤240（`settings presentation text is invalid`）。

解码后的 `PluginSettingField` 字段：`key`、`value_type`、`title`、`description`、
`required`、`default`、`choices`、`minimum`、`maximum`、`value_format`、`placeholder`。

持久化与读取：`PluginManager.settings()` / `replace_settings()` 走
`GET|PUT /api/plugins/{id}/settings`（§6）；插件在 `setup()` 里用
`runtime.setting(key, default)` 读（§4.2），保存后需重新加载插件才生效
（`runtime.settings` 是加载时快照）。

### 2.4 `kind: "theme_pack"`（纯 CSS，不执行 Python）

- 必须声明至少一个 `frontend.themes`：`theme_pack requires at least one frontend theme`。
- 反过来，`kind` 不是 `theme_pack` 却声明了 `themes`：
  `only theme_pack may declare frontend themes`。
- 每个主题对象只读 `id`、`title`、`asset`、`mode` 四个键：

| 键 | 约束 | 失败信息 |
|----|------|----------|
| `id` | 匹配 `^[a-z][a-z0-9_-]{1,63}$`，整包唯一 | `theme id and title are invalid` / `theme ids must be unique` |
| `title` | 非空，≤120 | `theme id and title are invalid` |
| `asset` | 必须已列在 `frontend.assets` 中且以 `.css` 结尾 | `theme asset must be a whitelisted CSS file` |
| `mode` | `dark` 或 `light` | `theme mode must be dark or light` |

主题包**不允许**声明 `entry`（`only tool plugins may declare entry`），也不允许声明
`frontend.panels`。`PluginManager._load()` 对非 `tool` 插件直接返回、不 import 任何代码。

```json
{
  "name": "midnight-skin",
  "display_name": "Midnight Skin",
  "version": "1.0.0",
  "api_version": "1",
  "kind": "theme_pack",
  "description": "示例主题包：只提供 CSS 变量覆盖。",
  "frontend": {
    "assets": ["midnight.css"],
    "themes": [
      {"id": "midnight", "title": "午夜", "asset": "midnight.css", "mode": "dark"}
    ]
  }
}
```

### 2.5 `frontend.panels`（一次性输入，宿主渲染）

只有 `kind: "tool"` 可以声明面板，因为 action 必须由 Python `setup()` 显式注册（§4.4）。
完整用法见 [plugin-panel-manifest.md](plugin-panel-manifest.md)。

面板对象允许的键：`id`、`title`、`description`、`action`、`submit_label`、`fields`
（未知键报 `frontend panel contains an unknown property`）。

| 键 | 约束 | 缺省 |
|----|------|------|
| `id` | 匹配 `^[a-z][a-z0-9_-]{1,63}$`，整包唯一（`frontend panel ids must be unique`） | 必填 |
| `action` | 同一正则，整包唯一（`frontend panel actions must be unique`） | 必填 |
| `title` | ≤120 | `id` |
| `description` | ≤1000 | 空 |
| `submit_label` | ≤120 | `Run` |
| `fields` | 字段对象数组（见下） | 空 |

字段对象允许的键：`key`、`type`、`title`、`description`、`required`、`default`、`enum`、
`minimum`、`maximum`、`format`、`placeholder`、`sensitive`、`visible_if`
（未知键报 `frontend panel field contains an unknown property`）。

- `key` 匹配 `^[a-z][a-z0-9_-]{0,119}$`，面板内唯一（`frontend panel field keys must be unique`）。
- `type` ∈ `string` / `integer` / `number` / `boolean`。
- `sensitive` 必须与「键名形状」一致：键名含凭据字样时必须为 `true`，不含时必须为 `false`，
  否则 `credential-shaped panel keys must be explicitly sensitive`。
- `sensitive: true` 要求 `type: "string"` + `"format": "password"` + 不写 `default`：
  `sensitive panel fields require string password format and no default`。
- `format` ∈ `uri` / `path` / `textarea` / `password`，且只能用于 `string`；
  `"password"` 必须配 `sensitive: true`（`password panel format requires sensitive=true`）。
- `default` / `enum` 的值必须匹配 `type`；`minimum`/`maximum` 仅数值类型且 `minimum <= maximum`。
- `visible_if` 是声明式可见性条件，允许 `key`、`equals`、`one_of`、`not_empty`、`all`、`any`，
  嵌套深度上限 4，且至少要有一个条件。

### 2.6 会被拒绝的写法（旧文档里出现过）

```text
# 1. 未知顶层字段（author / license / tools / dependencies / checksum 都不存在）
{"name": "demo", "version": "0.1.0", "api_version": "1", "entry": "main",
 "author": "me", "license": "MIT", "tools": ["x"], "checksum": "sha256:..."}
→ ManifestError: unknown manifest fields: author, checksum, license, tools

# 2. 旧版 entry_type
{"name": "demo", "version": "0.1.0", "api_version": "1", "entry": "main",
 "entry_type": "module"}
→ ManifestError: unknown manifest fields: entry_type

# 3. frontend 里写命令清单
{"frontend": {"assets": ["plugin.js"], "commands": ["demo:search"]}}
→ ManifestError: unknown frontend fields: commands

# 4. panels 写成字符串数组
{"frontend": {"panels": ["lookup"]}}
→ ManifestError: every frontend panel must be an object

# 5. 非 tool 插件声明 entry
{"kind": "theme_pack", "entry": "main"}
→ ManifestError: only tool plugins may declare entry

# 6. tool 插件的 entry 写成文件名
{"kind": "tool", "entry": "main.py"}
→ ManifestError: tool plugin entry must be a Python module name

# 7. settings_schema 没开 frontend.settings
{"frontend": {"settings": false}, "settings_schema": [{"key": "a", "type": "string"}]}
→ ManifestError: settings_schema requires frontend.settings=true

# 8. 想在 settings_schema 里存 API Key
[{"key": "api_key", "type": "string"}]
→ ManifestError: settings key is invalid or credential-shaped

# 9. 静态资源穿越
{"frontend": {"assets": ["../secret.js"]}}
→ ManifestError: frontend asset must be a safe relative path
```

---

## 3. 权限（声明 + 用户确认，无运行时强制）

`permissions` 是 `{action, scope}` 对象数组。代码只校验「非空字符串 + 长度上限」：

| 字段 | 约束 | 失败信息 |
|------|------|----------|
| `action` | 非空字符串，≤80 字符 | `permission action and scope must be bounded strings` |
| `scope` | 非空字符串，≤500 字符 | 同上 |

即：

- **没有枚举**：`action` 写什么都能通过校验。`shell`、`network`、`http`、`fs.read`、
  `fs.write`、`env`、`connector.read`、`connector.write`、`event.subscribe` 只是仓库内插件
  实际使用的取值（见 `plugins/*/manifest.json`），不是白名单。
- 不校验 `scope` 语法，也不在解析期去重。

授予与确认：`PluginManager.load(plugin_id, grant_permissions=...)` 计算
「清单声明 − 已授予」的差集；差集非空且 `grant_permissions=False` 时抛
`ValueError("plugin permissions require explicit confirmation")`（HTTP 侧映射为 409）；
`grant_permissions=True` 时把差集并入 `permissions_granted` 并持久化。
启动恢复（`restore_enabled()`）固定用 `grant_permissions=False`，所以只有**之前确认过**
权限的插件会自动回到 `active`。

**没有运行时强制**：代码中不存在按 `permissions` 拦截工具调用、文件访问或网络请求的分支；
`permissions_granted` 只出现在加载、状态投影（`permissions_granted` 字段）与注册表读写路径。
也就是说权限是**给用户看的确认清单**，不是沙箱边界。插件代码与宿主同进程、同权限运行；
真正的隔离手段是 §4.3 的工具命名空间、§6 的端点边界与卸载吊销。

---

## 4. 入口模块与 PluginRuntime

### 4.1 `_load()` 实际流程

1. `kind != "tool"`：直接返回、**不 import 任何 Python**（`ui` / `theme_pack` 只是声明包）。
2. `entry` 为空：`RuntimeError("tool plugin is missing an entry module")`。
3. 模块名 `angelus_plugins_<name>`（`-` 替换成 `_`），源码取 `<package_path>/<entry>.py`，
   以 `submodule_search_locations=[<package_path>]` 装载，因此插件可以用相对导入访问同目录模块。
4. 模块必须暴露 `angelus_plugin`，且其 `setup` 可调用；否则
   `RuntimeError("plugin module must expose angelus_plugin.setup(runtime)")`。
   `teardown` 缺失时宿主注入空实现，所以 `teardown` 是可选的。
5. 构造 `PluginRuntime(manifest, record.settings, "<plugin_root>/data/<id>")` 并 `mkdir` 该目录（§8）。
6. 调 `setup(runtime)`；随后校验 UI action 集合（§4.4）、发布工具提供者（§4.3）。
7. 任一步抛异常：清掉该模块命名空间（含相对导入的子模块），抛
   `RuntimeError("plugin setup failed: <ExcType>: <msg>")`。插件停在未加载状态，宿主进程不受影响。

`AngelusCore.__init__` 的装配顺序：`PluginManager(state_root, tool_registry,
development_root, managed_root)` → `restore_enabled()`，后者对每个 `enabled=True` 的记录调
`load(id, grant_permissions=False)` 并吞掉 `KeyError` / `RuntimeError` / `ValueError`——
坏包不会挡住 Angelus 启动，但仍会以 `state: "error"` / 未加载状态出现在工作台里。

同一插件重复 `load` 不会重复发布：`_loaded` 里已有该名字时直接返回 `active` 状态。

### 4.2 PluginRuntime API

`PluginRuntime` 是普通 `@dataclass`（非 frozen），字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `plugin` | `PluginManifest` | 正在执行的清单 |
| `settings` | `tuple[PluginSettingValue, ...]` | 加载时的设置快照（只读元组，用 `setting()` 取值） |
| `state_path` | `str` | 插件私有目录 `<plugin_root>/data/<id>`，加载前已创建 |
| `contributions` | `list[PluginToolContribution]` | `setup()` 期间暂存的工具贡献 |
| `context_contributions` | `list[PluginContextContribution]` | 暂存的 Composer 上下文贡献 |
| `ui_actions` | `list[PluginUiActionRegistration]` | 暂存的 UI action 注册 |

方法**只有 4 个**：

| 方法 | 签名 | 语义 |
|------|------|------|
| `register_tool_provider` | `(contribution: PluginToolContribution) -> None` | 暂存一个工具贡献；`setup()` 正常返回后才发布（§4.3） |
| `register_context_provider` | `(contribution: PluginContextContribution) -> None` | 暂存 Composer 上下文源；`roles` 缺省 `frozenset({"coordinator", "worker"})` |
| `register_ui_action` | `(action_id: str, handler) -> None` | 暂存面板 action handler（§4.4） |
| `setting` | `(key: str, default=None)` | 读一条已保存设置，缺失返回 `default` |

最小入口示例（注册一个工具贡献）：

```python
from angelus.modules.plugin_module import (
    PluginToolCategory,
    PluginToolContribution,
    PluginToolDefinition,
)
from llmfetcher import Tool, ToolParameter, ToolSchema


class Provider:
    def materialize(self, session_id, policy, role):
        return [
            Tool(
                "plugin.hello-tool.greet",
                "Greet one user.",
                ToolSchema(properties=[ToolParameter("name")]),
                lambda name="world": f"hello {name}",
            ),
        ]


class Plugin:
    def setup(self, runtime):
        runtime.register_tool_provider(
            PluginToolContribution(
                provider=Provider(),
                categories=(PluginToolCategory("utility", "Utility", "Helper tools"),),
                definitions=(
                    PluginToolDefinition(
                        "greet", "utility", "Greet", "Greet one user.",
                        frozenset({"coordinator", "worker"}),
                    ),
                ),
            )
        )

    def teardown(self):
        return None


angelus_plugin = Plugin()
```

`materialize(session_id, policy, role)` 是宿主对 provider 的唯一调用约定；
`PluginContextProvider` 对应 `materialize_context(session_id, role, agent_name)`。

### 4.3 工具发布、命名空间与吊销

`_publish()` 把 `setup()` 暂存的贡献变成全局注册项：

- provider 注册 ID：`plugin.<name>.<index>`（`index` 是本次贡献的序号）。
- 类别 ID：`plugin.<name>.<category id>`；工具 ID：`plugin.<name>.<tool id>`；
  `ToolDefinition` 绑定 provider ID、类别、`roles`。
- 约束：`categories` 不能为空，且每个 `definitions` 的 `category_id` 必须是本次贡献声明的类别，
  否则 `RuntimeError("plugin contribution has invalid categories")`。
- 发布中途失败会把本次已注册的 provider 全部 `unregister`（原子性）。

物化时（`_PluginProvider.materialize`）：

1. 已吊销 → 返回空列表。
2. provider 返回的每个 Tool 名必须以 `plugin.<name>.` 开头，否则
   `RuntimeError("plugin emitted a Tool outside its namespace")`。
3. 按类别映射 + 会话 `ToolPolicy` 过滤。
4. 每个 Tool 都被换成「可吊销」句柄：卸载后调用抛
   `ToolCallValidationError("tool '<id>' is no longer available: its plugin was unloaded")`。
   已经开始的那次调用继续跑完（它持有原 handler），之后的重物化与调用一律被拒。

卸载（`unload`）动作：unregister 全部 provider → 调 `teardown()`（异常被吞）→ 清模块命名空间
→ 记录翻回 `enabled=False`。包目录与设置**保留**，不会删除插件文件。

### 4.4 UI action 的强制校验

`_validate_ui_actions()` 要求：`setup()` 里注册的 action id 集合与 manifest 全部 panel 的
`action` 集合**完全相等**。

| 情况 | 结果 |
|------|------|
| action id 重复注册 | `RuntimeError("plugin registered duplicate panel actions")` |
| 有 panel 缺 handler，或注册了未声明的 action | `RuntimeError("plugin panel actions do not match manifest")` |
| handler 不可调用 | `RuntimeError("plugin panel action handler is not callable")` |

以上任一失败都发生在 `setup()` 之后、插件真正进入 `active` 之前，整包加载失败（§4.1 第 7 步）。

`invoke_panel(plugin_id, panel_id, values)` 的失败分类：

| 条件 | 异常 | HTTP |
|------|------|------|
| 插件未知 / 未加载 / panel 未声明 | `KeyError` | 404 `active plugin panel not found` |
| 提交值不是 JSON 对象 | – | 422 `plugin panel values must be an object` |
| action 未注册 | `RuntimeError("plugin panel action is not registered")` | 422 |
| 字段校验失败（缺 `required`、类型/enum/范围/format 不符） | `ValueError` | 422 |
| handler 抛异常 | `RuntimeError("plugin panel action failed: <Type>: <msg>")` | 422 |
| handler 返回值不是 `PluginUiActionResult` | `RuntimeError("plugin panel action must return PluginUiActionResult")` | 422 |

---

## 5. 未实现（旧文档声称、代码中不存在）

这一节是本文最重要的部分：以下能力在仓库里**没有任何实现**，不要按它们写代码或写计划。

| 旧文档的写法 | 现状 | 代码事实 |
|--------------|------|----------|
| `angelus/plugins/base.py` 里的 `AngelusPlugin` 基类、`HOOK_EVENTS` 常量 | 不存在该模块 | 入口只需要一个暴露 `angelus_plugin`、具备可调用 `setup(runtime)` 的对象；没有基类、没有事件常量 |
| `runtime.register_hook(...)` | 不存在 | `PluginRuntime` 只有 §4.2 的 4 个方法 |
| `runtime.register_route(...)` 与 `/plugins/<name>/api` 前缀 | 不存在 | 插件无法注册 HTTP 路由；`angelus/api/plugins.py` 里只有宿主自己的端点（§6） |
| `runtime.register_connector(...)`、`GET /api/providers` 合并插件 provider | 不存在 | 插件不能扩展连接器；连接器仍由 `angelus/connectors.py` 独占 |
| `bridge_tools` / `bridge_hooks` / `bridge_routes` / `bridge_connectors` 桥接层 | 不存在 | 工具接入点就是 `ToolRegistry`（§4.3），没有独立桥接模块 |
| 事件白名单（`agent.started`、`tool.before`、`session.created` 等点命名事件） | 不存在 | 无钩子注册面，也没有映射到 `llmfetcher/events.py` 的代码 |
| CLI `angelus plugin install/list/enable/disable/uninstall` | 不存在 | `angelus/cli.py` 只有两个子命令：`session`（`list` / `create`）与 `web`（`--host` / `--port`） |
| `ANGELUS_PLUGIN_AUTORELOAD` 热重载 | 不存在 | 无该环境变量；改代码后必须重新 `load` |
| `checksum` 字段与安装期完整性校验 | 不存在 | 字段本身被拒绝（§2.6）；也没有安装流程 |
| `plugins.json` 注册表文件 | 已改名 | 现在是 `<plugin_root>/registry.json`，结构 `{"schema_version": 1, "plugins": [...]}`（§8） |
| `GET /api/plugins/{id}` 单插件详情 | 不存在 | 只有 `GET /api/plugins`（active 集合）与 `GET /api/plugins/status`（全部发现项），列表里已含完整状态对象（§6） |
| 权限运行时门（例如 `check_permission`） | 不存在 | 见 §3：只有声明与确认 |
| manifest 的 `author` / `license` / `tools` / `dependencies` / `entry_type` | 被拒绝 | 见 §2.6 |
| `frontend.commands`、`panels` 为字符串数组 | 被拒绝 | `frontend` 只接受 `assets` / `settings` / `themes` / `panels`，且 panels 是对象数组（§2.2、§2.5） |
| `surface` / `slot` 之类的 UI 挂载点 | 不存在 | `frontend` 没有这两个键；UI 挂载只有静态资源与声明式面板 |

前端方面的真实状态见 §6.1 与 [plugin-guide.md](plugin-guide.md) §7：
`window.Angelus` 桥只存在于**遗留工作台**（`frontend/static/plugins.js`），
GEOINT 界面只提供生命周期与设置管理，不加载插件的 `plugin.js` / `plugin.css`。

---

## 6. 宿主 HTTP 端点

`angelus/api/plugins.py` 的全部路由（无其它插件相关端点）：

| 方法 | 路径 | 请求体 | 响应 | 主要错误 |
|------|------|--------|------|----------|
| GET | `/api/plugins` | – | `{"plugins": [...]}`，**仅 active** 且可被浏览器加载的包 | – |
| GET | `/api/plugins/status` | – | `{"plugins": [...]}`，全部发现项与注册项 | – |
| POST | `/api/plugins/rescan` | – | `{"discovered": <扫描到的包目录数>}`；**不执行**插件代码 | – |
| POST | `/api/plugins/discovered/{name}/register` | `{"confirm": true}` | `{"plugin": <状态对象>}`；只登记目录、不执行代码 | 422 `plugin registration requires confirm=true`；404 `unknown valid discovered plugin` |
| POST | `/api/plugins/{plugin_id}/load` | `{"confirm": true, "grant_permissions": bool}` | `{"plugin": <状态对象>}` | 422 `plugin load requires confirm=true`；404 `unknown plugin`；409 `plugin permissions require explicit confirmation`；422 `plugin setup failed: ...` |
| POST | `/api/plugins/{plugin_id}/unload` | `{"confirm": true}` | 未激活状态对象 | 422 `plugin unload requires confirm=true`；404 `unknown plugin` |
| GET | `/api/plugins/{plugin_id}/settings` | – | `{"id","name","settings","settings_schema","panels"}` | 404 `plugin settings are unavailable`（未注册或未开 `frontend.settings`） |
| PUT | `/api/plugins/{plugin_id}/settings` | 设置键值对象 | `{"id","name","settings"}` | 422 `plugin settings must be an object`；404 同上；422 校验错误原文 |
| POST | `/api/plugins/{plugin_id}/panels/{panel_id}/invoke` | 面板字段对象 | `{"title","content","tone"}` | 422 `plugin panel values must be an object`；404 `active plugin panel not found`；422 其它（§4.4） |
| GET | `/plugins/{name}/static/{asset}` | – | 白名单静态文件 | 404 `plugin asset not found` |

**没有** `GET /api/plugins/{plugin_id}`：状态一律从两个列表端点里取（列表项已包含
`id`、`name`、`display_name`、`version`、`kind`、`state`、`error`、`registered`、`enabled`、
`settings_available`、`permissions_requested`、`permissions_granted`、`themes`、`panels`）。

`state` 取值只有 4 个：`discovered`（发现、未注册）、`inactive`（已注册、未加载）、
`active`（已加载）、`error`（清单不合法，此时其它字段为最小安全投影，`error` 为原文）。

### 6.1 静态资源

`GET /plugins/{name}/static/{asset}` 的判定链（`PluginManager.static_asset`）：

1. 插件必须是**当前已加载**的（不在 `_loaded` 里 → 404）。
2. `asset` 必须按原始字符串出现在该插件 manifest 的 `frontend.assets` 中（未声明 → 404）。
3. 解析后的真实路径必须位于包目录之内且是普通文件（防穿越 → 404）。

该路由 `include_in_schema=False`。IE 之外的资源（未列入 `assets` 的文件）永远拿不到。

---

## 7. `api_version` 策略

- `api_version` 必填、≤16 字符，且必须**精确等于** `"1"`，否则
  `ManifestError("api_version must be '1'")`。没有协商、没有区间、没有兼容旧版本的分支。
- 契约版本只影响「这份 manifest 能否被发现」；加载流程本身不读 `api_version`（§4.1）。
- 未来若要升版，宿主必须显式接受新的字面量，否则旧宿主会把新包判为 `state: "error"`——
  这一点是当前实现的安全默认值，不要依赖任何隐式回退。

---

## 8. 目录、注册表与发现根

### 8.1 一个插件 home

`PluginStore(state_root, managed_root=None)` 的布局：

```text
<plugin_root>/
├── package/          # 被扫描的插件包目录（每个子目录一个包）
├── data/<id>/        # 运行期私有目录（即 runtime.state_path，加载前自动创建）
├── registry.json     # {"schema_version": 1, "plugins": [<PluginRecord JSON>...]}，原子写
└── packages/         # 已废弃：重构前把包直接放在 home 下的老布局
```

- `plugin_root` = `ANGELUS_PLUGIN_DIR`（若非空）否则 `<state_root>/plugins`。
- `state_root` = `ANGELUS_STATE_DIR`（若非空）否则 `<cwd>/.angelus-state`。
- `packages/` 仍会被扫描，但只作为**兜底**（排在 canonical 根之后，重复名以 canonical 为准），
  且会打一次弃用警告——用于升级后不丢已注册的老包。
- `registry.json` 的 `schema_version` 不是 1、或 `plugins` 不是数组时抛
  `ValueError("invalid plugin registry")` / `ValueError("invalid plugin registry plugins")`。

### 8.2 发现根与优先级

`PluginManager` 的发现根顺序（`rescan()` 按此顺序遍历，先到先得；重名第二个包记为
`error: "duplicate plugin name: <name>"`）：

1. `<plugin_root>/package/`（受管插件）。
2. development 根：`ANGELUS_DISABLE_DEVELOPMENT_PLUGINS=1` 时指向
   `<cwd>/.angelus-no-development-plugins`（等于关闭开发根）；否则若设了
   `ANGELUS_BUNDLED_PLUGIN_ROOT` 就用它，否则 `<cwd>/plugins`（仓库自带的插件源码）。
3. 上述每个根的陈旧同名兄弟目录 `packages/`。

`scan` 只做声明式校验：`path.is_dir()` 且不是符号链接的目录才会被 `load_manifest()` 读取；
没有任何 `import`、没有代码执行，所以 `POST /api/plugins/rescan` 是安全操作。

### 8.3 工作目录中的 `plugins/`

仓库根的 `plugins/` 目录是**开发根**（§8.2 第 2 条），当前包含
`angelus-deepseek-balance-v0.1.0`、`async-download`、`pofp-ctf` 三个真实插件，
可以直接当参考实现读；没有任何示例插件会被安装流程复制到用户 home。
