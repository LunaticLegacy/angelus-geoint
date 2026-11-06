# Angelus 插件开发指南（v1）

> 上手路线：插件放哪 → `manifest.json` 怎么写 → `setup()` 里能做什么 → 怎么把包装载起来。
> 本文每一节都对应 `angelus/modules/plugin_module/` 里的实现；字段级约束与错误原文见
> [plugin-api.md](plugin-api.md)，声明式面板的字段清单见
> [plugin-panel-manifest.md](plugin-panel-manifest.md)。
>
> 旧版指南里的 hooks、HTTP 路由、连接器扩展点、插件安装命令、旧的注册表文件在代码里
> **从未实现**；§11 逐条列出，不要按那套写。

---

## 1. 插件包放在哪

### 1.1 一个 home，两类目录

插件只落在一个 home 下，**被扫描的包目录**与**运行期私有数据**是分开的：

```text
<plugin_root>/
├── package/
│   └── hello-tool/          # 被扫描的插件包：manifest.json + <entry>.py + 前端资源
│       ├── manifest.json
│       ├── main.py
│       └── plugin.css
├── data/
│   └── hello-tool/          # 就是 runtime.state_path，加载前由宿主 mkdir
├── registry.json            # 注册记录与已保存设置，原子写
└── packages/                # 已废弃的老布局，仅作兜底扫描
```

- `plugin_root` = `ANGELUS_PLUGIN_DIR`（非空时）否则 `<state_root>/plugins`。
- `state_root` = `ANGELUS_STATE_DIR`（非空时）否则 `<cwd>/.angelus-state`。
- `runtime.state_path` 是 `<plugin_root>/data/<plugin id>`，**在包目录之外**；
  插件自己产生的数据（缓存、下载、本地密钥文件）都应写在这里，不要写进包目录。
- 包目录名建议与 `manifest.name` 一致，但宿主以 manifest 的 `name` 为准：
  两个包声明同一个 `name` 时，后扫描到的那个直接判为
  `state: "error"`、`error: "duplicate plugin name: <name>"`。

### 1.2 开发时直接放进开发根

`rescan()` 按固定顺序扫描（先到先得）：

1. `<plugin_root>/package/`（受管包）；
2. 开发根：设了 `ANGELUS_BUNDLED_PLUGIN_ROOT` 就用它，否则 `<cwd>/plugins`；
   设 `ANGELUS_DISABLE_DEVELOPMENT_PLUGINS=1` 时开发根指向
   `<cwd>/.angelus-no-development-plugins`，等于关闭开发根；
3. 上述每个根的遗留兄弟目录 `packages/`。

仓库根的 `plugins/` 就是默认开发根，里面有三个可直接对照的真实插件：

| 包目录 | 用到的能力 |
|--------|------------|
| `angelus-deepseek-balance-v0.1.0` | 三个声明式面板（含 `sensitive` 密钥输入）、`settings_schema`、`plugin.js` / `plugin.css`、`tests/` |
| `async-download` | `register_tool_provider` + 面板，工具名严格带 `plugin.<name>.` 前缀 |
| `pofp-ctf` | 纯工具贡献 |

所以开发期最省事的做法是把包放到 `plugins/<name>/`，然后
`POST /api/plugins/rescan` 让宿主发现它。`rescan` 只读 `manifest.json`，不导入代码。

---

## 2. `manifest.json`

### 2.1 最小合法清单

```json
{
  "name": "hello-tool",
  "version": "0.1.0",
  "api_version": "1",
  "kind": "tool",
  "entry": "main"
}
```

这份清单能通过 `load_manifest()`：`display_name` 缺省取 `name`，`frontend` 缺省为空对象，
`permissions` / `settings_schema` 缺省为空。`manifest.json` 必须位于包目录根部。

### 2.2 顶层字段

顶层只允许 10 个键，其余一律拒绝（`unknown manifest fields: <按字母序逗号分隔>`）：

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `name` | string | ✅ | ≤64 字符，匹配 `^[a-z][a-z0-9_-]{1,63}$`（小写开头，最短 2 字符） |
| `display_name` | string | – | ≤120 字符，缺省取 `name` |
| `version` | string | ✅ | `^\d+\.\d+\.\d+$` |
| `api_version` | string | ✅ | 必须精确等于 `"1"` |
| `kind` | string | – | `tool` / `ui` / `theme_pack`，缺省 `tool` |
| `entry` | string | 仅 `kind=tool` | Python 模块名 `[A-Za-z_][A-Za-z0-9_]*`（写模块名，不写 `.py`）；其它 kind 出现即报错 |
| `description` | string | – | ≤2000 字符 |
| `permissions` | object[] | – | `{action, scope}` 数组，见 §8 |
| `frontend` | object | – | 只允许 `assets` / `settings` / `themes` / `panels` |
| `settings_schema` | object[] | – | 长期保存的标量配置，见 §6 |

`frontend` 的四个键：

| 键 | 约束 |
|----|------|
| `assets` | 字符串数组，唯一；每项是安全相对路径（不以 `/` 开头、不含 `..`），是静态资源的唯一白名单 |
| `settings` | 布尔，缺省 `false`；`settings_schema` 非空时必须为 `true` |
| `themes` | 仅 `kind: "theme_pack"` 可声明，每项 `{id, title, asset, mode}` |
| `panels` | 仅 `kind: "tool"` 可声明，必须是**面板对象数组**，见 §7 |

### 2.3 会被拒绝的写法

```text
{"name": "hello", "version": "0.1.0", "api_version": "1", "author": "me"}
→ unknown manifest fields: author

{"name": "hello", "version": "0.1.0", "api_version": "1", "entry_type": "module"}
→ unknown manifest fields: entry_type

{"name": "hello", "version": "0.1.0", "api_version": "1", "entry": "main.py"}
→ tool plugin entry must be a Python module name

{"name": "hello", "version": "0.1.0", "api_version": "1", "kind": "ui", "entry": "main"}
→ only tool plugins may declare entry

{"name": "hello", "version": "0.1.0", "api_version": "1",
 "frontend": {"commands": ["hello:search"]}}
→ unknown frontend fields: commands

{"name": "hello", "version": "0.1.0", "api_version": "1",
 "frontend": {"panels": ["lookup"]}}
→ every frontend panel must be an object

{"name": "hello", "version": "0.1.0", "api_version": "1",
 "settings_schema": [{"key": "limit", "type": "integer"}],
 "frontend": {"settings": false}}
→ settings_schema requires frontend.settings=true

{"name": "hello", "version": "0.1.0", "api_version": "1",
 "settings_schema": [{"key": "api_key", "type": "string"}],
 "frontend": {"settings": true}}
→ settings key is invalid or credential-shaped
```

密钥一类的输入不要放进 `settings_schema`，用面板的 `sensitive` 字段（§6）。

---

## 3. 入口模块与 `setup()`

只有当 `kind == "tool"` 时宿主才会导入 Python 代码；`ui` / `theme_pack` 完全不 import。
`_load()` 的实际动作：

- 入口文件是 `<package_path>/<entry>.py`；
- 模块名固定为 `angelus_plugins_<name 中 - 换 _>`，`submodule_search_locations`
  指向包目录，所以入口模块可以用相对导入加载同包内的子模块；
- 模块必须暴露 `angelus_plugin`，且它的 `setup` 可调用，否则
  `RuntimeError("plugin module must expose angelus_plugin.setup(runtime)")`；
- `teardown` 可选：缺失时宿主注入一个空实现；
- 构造 `PluginRuntime` 并 `mkdir` `state_path` 之后再调 `setup(runtime)`；
- 任一步抛异常 → `RuntimeError("plugin setup failed: <ExceptionType>: <msg>")`，
  插件回到未加载状态，宿主进程不受影响。

没有基类、没有装饰器、没有注册文件，只有一个对象：

```python
from pathlib import Path


class Plugin:
    def setup(self, runtime):
        Path(runtime.state_path, "loaded.txt").write_text("ready", encoding="utf-8")

    def teardown(self):
        return None


angelus_plugin = Plugin()
```

`setup()` 里可以调用的方法**只有 4 个**：

| 方法 | 用途 |
|------|------|
| `runtime.register_tool_provider(contribution)` | 注册工具贡献（§4） |
| `runtime.register_context_provider(contribution)` | 注册 Composer 上下文源（§5） |
| `runtime.register_ui_action(action_id, handler)` | 注册面板 action（§6） |
| `runtime.setting(key, default=None)` | 读一条已保存设置（§6） |

`runtime` 的字段：`plugin`（`PluginManifest`）、`settings`（加载时的设置快照）、
`state_path`（私有目录字符串）、`contributions` / `context_contributions` / `ui_actions`
（`setup()` 期间的暂存列表）。

约定：所有注册都只发生在 `setup()` 内，`setup()` 正常返回后宿主才把贡献发布出去；
中途失败会清掉该模块的命名空间（含相对导入进来的子模块）。

---

## 4. 注册工具：`register_tool_provider`

一次工具贡献由三个对象组成：

- `PluginToolContribution(provider, categories, definitions)`；
- `provider` 必须实现 `materialize(session_id, policy, role) -> list[Tool]`；
- `categories` 是 `PluginToolCategory(id, title, description)` 的元组，**不能为空**；
- `definitions` 是 `PluginToolDefinition(id, category_id, title, description, roles)` 的元组，
  每个 `category_id` 必须是本次贡献声明过的类别。

宿主在发布时加命名空间：

| 对象 | 最终 ID |
|------|---------|
| provider | `plugin.<name>.<序号>` |
| 类别 | `plugin.<name>.<category id>` |
| 工具 | `plugin.<name>.<tool id>` |

`materialize()` 返回的每个 `Tool` 名字都必须以 `plugin.<name>.` 开头，否则
`RuntimeError("plugin emitted a Tool outside its namespace")`；只有同时出现在
`definitions` 里（并写入类别映射）的工具才会真正交给 Agent。

```python
from angelus.modules.plugin_module import (
    PluginToolCategory,
    PluginToolContribution,
    PluginToolDefinition,
)
from llmfetcher import Tool, ToolParameter, ToolSchema


def greet(name="world"):
    return f"hello {name}"


class GreetProvider:
    def materialize(self, session_id, policy, role):
        return [
            Tool(
                "plugin.hello-tool.greet",
                "Greet one user by name.",
                ToolSchema(properties=[ToolParameter("name", "string", "User name", True)]),
                greet,
            ),
        ]


class Plugin:
    def setup(self, runtime):
        runtime.register_tool_provider(
            PluginToolContribution(
                provider=GreetProvider(),
                categories=(PluginToolCategory("utility", "Utility", "Helper tools"),),
                definitions=(
                    PluginToolDefinition(
                        "greet",
                        "utility",
                        "Greet",
                        "Greet one user by name.",
                        frozenset({"coordinator", "worker"}),
                    ),
                ),
            )
        )


angelus_plugin = Plugin()
```

`Tool` 的位置参数顺序是 `(name, description, schemas, handler)`；
`ToolSchema(properties=[...])`；`ToolParameter` 是
`(name, type="string", description="", required=True, enum=None, default=None)`。

卸载插件时宿主会 unregister 该插件的全部 provider、调 `teardown()`、清模块命名空间，
并把记录翻回未启用；包目录与设置保留。已经物化出去的 Tool 句柄会被替换成
「可吊销」版本，卸载后再调用会抛
`ToolCallValidationError("tool '<id>' is no longer available: its plugin was unloaded")`。

---

## 5. 注册 Composer 上下文源：`register_context_provider`

`PluginContextContribution(provider, roles)` 的 `roles` 缺省是
`frozenset({"coordinator", "worker"})`；宿主按当前 Agent 的 role 过滤后调用
`provider.materialize_context(session_id, role, agent_name)`，把返回列表里非 `None` 的项
交给 Composer。

返回的对象必须是 `llmfetcher.context_handlers` 里的 `ContextProvider`（一个 `Protocol`）：
它声明 `provider_id: str`，并实现 `build_blocks(snapshot) -> Sequence[ContextBlock]`。
上下文源只负责「把插件状态投影成请求里的块」，不能改写会话历史。

```python
from angelus.modules.plugin_module import PluginContextContribution


class NotesProvider:
    provider_id = "plugin.hello-tool.notes"

    def build_blocks(self, snapshot):
        return []

    def materialize_context(self, session_id, role, agent_name):
        return [self] if role == "worker" else []


class Plugin:
    def setup(self, runtime):
        runtime.register_context_provider(
            PluginContextContribution(
                provider=NotesProvider(),
                roles=frozenset({"worker"}),
            )
        )


angelus_plugin = Plugin()
```

上面的 `build_blocks` 返回空序列，表示这一轮不注入任何块——它是能跑通的最小实现；
真正的插件应在这里按 `snapshot` 组装自己的 `ContextBlock`。

---

## 6. 设置与面板 action

### 6.1 `settings_schema` + `runtime.setting()`

长期保存的非敏感配置写在 `settings_schema`，并要求 `frontend.settings: true`：

| 属性 | 约束 |
|------|------|
| `key` | `^[a-z][a-z0-9_-]{0,119}$`，整份 schema 内唯一，且不得含凭据字样（`api_key`/`apikey`/`token`/`password`/`secret`/`credential`） |
| `type` | `string` / `integer` / `number` / `boolean`，`default` 与 `enum` 必须与它精确匹配 |
| `enum` / `minimum` / `maximum` | 上下界只用于数值类型，且 `minimum <= maximum` |
| `format` | `uri` / `path` / `textarea`，只能用于 `string` |
| `title` / `description` / `placeholder` | ≤120 / ≤1000 / ≤240 |

保存路径是 `PUT /api/plugins/{plugin_id}/settings`（请求体是键值对象，未知键报
`unknown plugin fields: ...`）。插件侧用 `runtime.setting()` 读：

```python
class Plugin:
    def __init__(self):
        self.limit = 10

    def setup(self, runtime):
        value = runtime.setting("result_limit", 10)
        if isinstance(value, int) and not isinstance(value, bool):
            self.limit = value
```

`runtime.settings` 是**加载时快照**：用户改了设置后要重新 `unload` + `load`
（或重启宿主）才能读到新值。

### 6.2 `register_ui_action()`

面板（`frontend.panels`）只是声明；真正的处理函数由 `setup()` 注册，
两者必须**严格一一对应**——注册的 action id 集合与 manifest 里所有 panel 的
`action` 集合完全相等，否则整包加载失败：

| 情况 | 结果 |
|------|------|
| action id 重复注册 | `plugin registered duplicate panel actions` |
| 有 panel 缺 handler，或注册了未声明的 action | `plugin panel actions do not match manifest` |
| handler 不可调用 | `plugin panel action handler is not callable` |

handler 收到 `PluginUiActionRequest`（`request.value(key, default)` 取已校验的字段值），
必须返回 `PluginUiActionResult(title, content, tone)`，`tone` ∈ `info` / `success` / `error`。
返回值不是该类型会得到 `plugin panel action must return PluginUiActionResult`；
handler 抛异常会得到 `plugin panel action failed: <Type>: <msg>`。

```python
from angelus.modules.plugin_module import PluginUiActionResult


class Plugin:
    def setup(self, runtime):
        runtime.register_ui_action("lookup", self._lookup)

    def _lookup(self, request):
        query = request.value("query", "")
        if not isinstance(query, str) or not query:
            return PluginUiActionResult("参数缺失", "query 不能为空。", "error")
        return PluginUiActionResult("查询完成", f"query={query}", "success")


angelus_plugin = Plugin()
```

字段校验在宿主侧完成（缺 `required`、类型不符、越界、枚举外的值都是 422），
所以 handler 里只需要处理业务语义。宿主只把 `title` / `content` / `tone` 当纯文本回显，
不要指望返回值能注入 HTML。

---

## 7. 自包含完整示例

一个包同时提供：一个工具、一个声明式面板、一条长期设置。

### 7.1 `manifest.json`

```json
{
  "name": "hello-tool",
  "display_name": "Hello Tool",
  "version": "0.1.0",
  "api_version": "1",
  "kind": "tool",
  "entry": "main",
  "description": "示例插件：一个工具 + 一个声明式面板 + 一条长期设置。",
  "permissions": [
    {"action": "fs.read", "scope": "docs/**"}
  ],
  "frontend": {
    "assets": ["plugin.css"],
    "settings": true,
    "panels": [
      {
        "id": "lookup",
        "title": "关键词查询",
        "description": "按文件名关键词列出目录内容。",
        "action": "lookup",
        "submit_label": "查询",
        "fields": [
          {
            "key": "query",
            "type": "string",
            "title": "关键词",
            "required": true,
            "placeholder": "例如 heap"
          },
          {
            "key": "limit",
            "type": "integer",
            "title": "条数",
            "default": 10,
            "minimum": 1,
            "maximum": 50
          }
        ]
      }
    ]
  },
  "settings_schema": [
    {
      "key": "root_dir",
      "type": "string",
      "title": "扫描目录",
      "description": "留空时使用插件私有目录。",
      "format": "path",
      "default": ""
    }
  ]
}
```

### 7.2 `main.py`

```python
from pathlib import Path

from angelus.modules.plugin_module import (
    PluginToolCategory,
    PluginToolContribution,
    PluginToolDefinition,
    PluginUiActionResult,
)
from llmfetcher import Tool, ToolParameter, ToolSchema


def find_files(root_dir, query, limit):
    root = Path(root_dir).expanduser()
    if not root.is_dir():
        return {"error": f"目录不存在: {root}"}
    hits = sorted(path.name for path in root.iterdir() if query in path.name)[:limit]
    return {"query": query, "count": len(hits), "files": hits}


class FileProvider:
    def __init__(self, root_dir):
        self._root_dir = root_dir

    def materialize(self, session_id, policy, role):
        return [
            Tool(
                "plugin.hello-tool.find_files",
                "按文件名关键词列出目录内容。",
                ToolSchema(properties=[
                    ToolParameter("query", "string", "文件名关键词"),
                    ToolParameter("limit", "integer", "最多返回条数", True, None, 10),
                ]),
                lambda query, limit=10: find_files(self._root_dir, query, limit),
            ),
        ]


class Plugin:
    def __init__(self):
        self.root_dir = ""

    def setup(self, runtime):
        self.root_dir = runtime.setting("root_dir", runtime.state_path) or runtime.state_path
        runtime.register_ui_action("lookup", self._lookup)
        runtime.register_tool_provider(
            PluginToolContribution(
                provider=FileProvider(self.root_dir),
                categories=(PluginToolCategory("files", "Files", "文件系统工具"),),
                definitions=(
                    PluginToolDefinition(
                        "find_files",
                        "files",
                        "Find files",
                        "按文件名关键词列出目录内容。",
                        frozenset({"coordinator", "worker"}),
                    ),
                ),
            )
        )

    def _lookup(self, request):
        query = request.value("query", "")
        limit = request.value("limit", 10)
        result = find_files(self.root_dir, query, limit)
        if "error" in result:
            return PluginUiActionResult("查询失败", result["error"], "error")
        return PluginUiActionResult("命中", f"{result['count']} 个文件", "success")

    def teardown(self):
        return None


angelus_plugin = Plugin()
```

### 7.3 从扫描到调用

把 `manifest.json` + `main.py` + `plugin.css` 放进 `plugins/hello-tool/`，然后按序调用宿主端点：

```text
POST /api/plugins/rescan
→ {"discovered": 4}

POST /api/plugins/discovered/hello-tool/register
body {"confirm": true}
→ {"plugin": {... "state": "inactive" ...}}      # 只登记目录，不执行代码

POST /api/plugins/hello-tool/load
body {"confirm": true, "grant_permissions": false}
→ 409 plugin permissions require explicit confirmation

POST /api/plugins/hello-tool/load
body {"confirm": true, "grant_permissions": true}
→ {"plugin": {... "state": "active" ...}}

POST /api/plugins/hello-tool/panels/lookup/invoke
body {"query": "heap", "limit": 5}
→ {"title": "命中", "content": "2 个文件", "tone": "success"}

POST /api/plugins/hello-tool/unload
body {"confirm": true}
→ {"plugin": {... "state": "inactive" ...}}
```

细节：

- 少了 `confirm: true` 一律 422（`plugin load requires confirm=true` 等），
  未知插件 404，`setup()` 抛异常 422 且 `detail` 以 `plugin setup failed:` 开头。
- `GET /api/plugins` 只返回 active 的包；要看全部发现项用 `GET /api/plugins/status`。
- 面板调用要求插件处于 active，未加载/面板未声明是 404 `active plugin panel not found`，
  字段非法与 handler 失败都是 422。
- 状态只有 4 种：`discovered`（发现未注册）、`inactive`（已注册未加载）、
  `active`（已加载）、`error`（清单不合法，`error` 字段是原文）。

---

## 8. 权限：声明 + 确认，没有运行时强制

`permissions` 是 `{action, scope}` 对象数组；`action` 与 `scope` 只校验为有界字符串
（`action` ≤80、`scope` ≤500），**没有枚举**，写成 `network` / `fs.read` / 你们自己的
动作名都能通过。

真实语义只有一条：加载时的确认。

- `load` 的请求体里 `grant_permissions` 为 `false`，而 manifest 声明的权限尚未全部授予时，
  返回 **409** `plugin permissions require explicit confirmation`；
- 授予后写入 `registry.json` 的记录（`permissions_granted`），之后再次加载不再重复确认；
- **加载之后没有任何运行时权限门**：插件代码是普通 Python，模型/文件/网络访问不会被
  `action` 截获，宿主也没有 `check_permission` 之类的钩子。所以 `permissions` 目前的定位是
  「向用户说明这个包需要什么」+「把确认动作留在加载这一步」，不要把它当沙箱。
- 卸载例外：`POST /api/plugins/{id}/unload` 会顺带清掉各 Session profile 里
  `plugin.<id>.` 前缀的工具权限项，避免旧会话把已卸载插件的工具开关复活。

---

## 9. 前端资源与 `window.Angelus`

### 9.1 静态资源

只有列在 `frontend.assets` 里的文件才能通过 `GET /plugins/{name}/static/{asset}` 拿到：
插件必须处于 active、`asset` 必须与声明字符串**完全一致**、解析后的真实路径必须落在包目录内
且是普通文件，否则一律 404。该路由不出现在 OpenAPI 文档里。

### 9.2 两套宿主界面，能力不同

| 宿主面 | 渲染方式 | 是否会加载插件的 `plugin.js` / `plugin.css` |
|--------|----------|--------------------------------------------|
| 遗留工作台（`frontend/templates/index.html` + `frontend/static/plugins.js`） | 读取 `GET /api/plugins`，把声明式面板渲染进 `.inspector-panels` 容器 | 会：固定注入每插件的 `plugin.js` 与 `plugin.css`（`theme_pack` 只注入 CSS） |
| GEOINT（`frontend/templates/geoint.html` 的 `data-panel="plugins"`） | `frontend/geoint-src/components/plugin-panel.js` 的 `mountPluginPanel()`：生命周期、设置、声明式面板表单，只调文档化端点 | **不会**：GEOINT 页面不加载插件的 `plugin.js` / `plugin.css` |

结论：声明式面板（`frontend.panels`）是唯一在两套界面都能用的插件 UI；
自有 JS 只有遗留工作台能看到。

### 9.3 `window.Angelus` 桥（仅遗留工作台）

桥只有三个入口，没有第四个：

- `window.Angelus.registerPanel(plugin, spec)`：往工作台 inspector 加一个面板；
  `spec.render` 可以是函数、HTML 字符串或 `Element`；
- `window.Angelus.registerCommand(plugin, spec)`：注册一个命令，`spec.handler` 必须是函数；
- `window.Angelus.registerSettings(plugin, spec)`：提供设置页的标题与说明。

这些调用发生在插件自己的 `plugin.js` 里（`plugin.js` 由工作台的加载器以
`/plugins/<name>/static/plugin.js` 注入）。manifest 里不需要、也不能声明命令清单。

`frontend.assets` 与脚本注入是两件事：`plugin.js` 即使没写进 `assets`
也会被尝试注入，但写进去才拿得到 200。

---

## 10. 调试与 pytest

| 现象 | 排查 |
|------|------|
| 列表里 `state: "error"` | `error` 字段就是 `ManifestError` 原文；对照 §2.2 / §2.3 逐条改清单 |
| 加载报 `plugin setup failed: ...` | 入口导入或 `setup()` 抛异常；括号里是异常类型与消息，模块命名空间已被清掉，可修完直接重试 `load` |
| 加载报 `plugin panel actions do not match manifest` | §6.2：注册的 action 集合与 manifest 面板声明不一致 |
| 工具调用找不到 `plugin.<name>.<tool>` | 确认插件 active、`materialize()` 返回的 Tool 名字带前缀、且 `definitions` 里声明了同一 id |
| 静态资源 404 | 插件未加载 / 文件没写进 `frontend.assets` / 路径与声明不一致 |
| 改了设置不生效 | `runtime.settings` 是加载时快照，重新 unload + load |
| 面板调用 422 | 字段类型/必填/范围不符，或 handler 抛异常（`plugin panel action failed: ...`） |

本地门禁（仓库根目录）：

```text
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m pytest tests\test_plugin_docs.py -q
```

`tests/test_plugin_manager.py` 覆盖发现/注册/加载/卸载/设置/面板调用；
`tests/test_plugin_docs.py` 是本套文档的防漂移门禁——它把三份文档里的每个 `json` 代码块
喂给 `load_manifest()`，并要求 `PluginRuntime` 的 4 个方法名与 16 个公开导出都出现在
`plugin-api.md` 里。所以改文档里的 JSON 示例时，示例必须是能被真实校验器接受的完整清单。

---

## 11. 不要再按这套写（代码中不存在）

| 旧指南的写法 | 现状 |
|--------------|------|
| `from angelus.plugins import AngelusPlugin`、`AngelusPlugin` 基类、事件常量表 | 没有 `angelus/plugins/` 包；入口只是一个暴露 `angelus_plugin` 的对象 |
| `runtime.register_hook(...)` 与事件白名单 | `PluginRuntime` 只有 4 个方法（§3），没有事件订阅面 |
| `runtime.register_route(...)`、`/plugins/<name>/api` 前缀 | 插件不能注册 HTTP 路由 |
| `runtime.register_connector(...)`、并入 `GET /api/providers` | 插件不能扩展连接器 |
| `bridge_tools` / `bridge_hooks` / `bridge_routes` / `bridge_connectors` 模块 | 不存在；工具接入点就是 `ToolRegistry`（§4） |
| `angelus plugin install / list / enable / disable / uninstall` | CLI 只有 `session`（`list`/`create`）与 `web`（`--host`/`--port`） |
| 旧的 `plugins.json` 注册表 | 现在是 `<plugin_root>/registry.json`（`{"schema_version": 1, "plugins": [...]}`） |
| `checksum` 字段与安装期完整性校验 | 字段本身被拒绝（§2.3 的未知字段），也没有安装流程 |
| 基于 `ANGELUS_PLUGIN_AUTORELOAD` 的热重载 | 没有该环境变量；改代码后必须重新 `load` |
| `GET /api/plugins/{id}` 单插件详情 | 没有；状态从 `GET /api/plugins` 与 `GET /api/plugins/status` 两个列表取 |
| `frontend.commands`、`panels: ["lookup"]` | 都被拒绝（§2.3）；`panels` 必须是对象数组 |
| `surface` / `slot` 之类的 UI 挂载点 | `frontend` 没有这两个键 |
