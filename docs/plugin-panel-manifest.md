# 声明式插件功能面板（`frontend.panels`）

Angelus 插件可以在 `manifest.json` 里声明由宿主渲染的功能面板：用户只会看到
插件作者声明的输入控件和提交按钮，manifest 不能注入 HTML、JavaScript 或任意
HTTP 路由。面板是**一次性输入**通道，提交值不落盘，因此也可以安全地承载密码、
令牌这类只用于本次调用的值。

## 1. 事实基线

| 位置 | 职责 |
|------|------|
| `angelus/modules/plugin_module/manifest.py` | `_panels()` / `_panel_fields()` 解析并校验 `frontend.panels`，不合格抛 `ManifestError`（`ValueError` 子类）；解析过程不导入插件代码 |
| `angelus/modules/plugin_module/models.py` | `PluginPanel`、`PluginPanelField`、`PluginUiActionRequest`、`PluginUiActionResult`、`PluginUiActionRegistration` |
| `angelus/modules/plugin_module/manager.py` | `invoke_panel()` 校验提交值并派发 action；`_validate_ui_actions()` 校验 action 注册集合；`_panel_json()` 生成 `GET /api/plugins/status` 的面板投影 |
| `angelus/api/plugins.py` | `POST /api/plugins/{plugin_id}/panels/{panel_id}/invoke` |
| `frontend/geoint-src/components/plugin-panel.js` | GEOINT 宿主：`mountPluginPanel()` 渲染面板并调用上述端点 |
| `frontend/static/plugins.js` | 遗留工作台宿主：加载 `plugin.js` / `plugin.css` 并提供 `window.Angelus` 桥 |

面板只在 `kind: "tool"` 插件上可用，因为 action handler 必须由 Python 的
`setup()` 显式注册（见 §4）。

## 2. 与 `settings_schema` 的分工

| 维度 | `settings_schema` | `frontend.panels` |
|------|-------------------|-------------------|
| 用途 | 长期保存的非敏感配置 | 一次性功能输入 |
| 是否落盘 | 是：`PUT /api/plugins/{plugin_id}/settings` 校验后写入注册表 | 否：只存在于本次 invoke 请求体 |
| 插件侧读取 | `runtime.setting(key, default)`（加载时快照，改完需重新加载） | `PluginUiActionRequest.value(key, default)` |
| 凭据类值 | 禁止：字段 `key` 含凭据字样直接 `ManifestError` | 允许，但必须 `sensitive: true` + `format: "password"` + 无 `default`（见 §3.5） |
| 前置条件 | 写 `settings_schema` 必须同时 `frontend.settings: true`（否则 `settings_schema requires frontend.settings=true`） | 必须 `kind: "tool"` 且有 `entry`（否则 `frontend panels require a tool plugin entry`） |

## 3. Manifest 中声明面板

### 3.1 位置与前值

面板写在 `frontend.panels`。`frontend` 只接受 4 个键 `assets`、`settings`、
`themes`、`panels`，其他键报 `unknown frontend fields: ...`。

### 3.2 完整可加载示例

下面这份 `manifest.json` 同时声明了一个面板和一条长期设置，可直接通过
`load_manifest()` 校验：

```json
{
  "name": "kb-lookup",
  "display_name": "知识查询",
  "version": "1.0.0",
  "api_version": "1",
  "kind": "tool",
  "entry": "main",
  "description": "查询本地知识库条目。",
  "frontend": {
    "assets": [],
    "settings": true,
    "panels": [
      {
        "id": "lookup",
        "title": "知识查询",
        "description": "查找本地知识，结果不会保存。",
        "action": "lookup",
        "submit_label": "查询",
        "fields": [
          {
            "key": "query",
            "type": "string",
            "title": "关键词",
            "required": true,
            "placeholder": "输入查询内容"
          },
          {
            "key": "mode",
            "type": "string",
            "title": "匹配方式",
            "enum": ["exact", "fuzzy"],
            "default": "fuzzy"
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
      "key": "result_limit",
      "type": "integer",
      "title": "默认结果数",
      "default": 10,
      "minimum": 1,
      "maximum": 100
    }
  ]
}
```

### 3.3 `panel` 对象允许的键

除这 6 个键以外的任何键都报 `frontend panel contains an unknown property`。

| 键 | 必填 | 约束 | 默认值 / 错误 |
|----|------|------|---------------|
| `id` | 是 | 匹配 `^[a-z][a-z0-9_-]{1,63}$`；同一 manifest 内唯一 | `frontend panel id is invalid`、`frontend panel ids must be unique` |
| `action` | 是 | 同一正则；同一 manifest 内唯一 | `frontend panel action is invalid`、`frontend panel actions must be unique` |
| `title` | 否 | ≤120 字符 | 默认取 `id` |
| `description` | 否 | ≤1000 字符 | 默认空串 |
| `submit_label` | 否 | ≤120 字符 | 默认 `"Run"` |
| `fields` | 否 | 数组，元素见 §3.4；可省略（空面板） | `frontend panel fields must be an array` |

### 3.4 `fields` 元素允许的键

字段对象出现未知键报 `frontend panel field contains an unknown property`。

| 键 | 约束 | 错误消息 |
|----|------|----------|
| `key` | 匹配 `^[a-z][a-z0-9_-]{0,119}$`；面板内唯一 | `frontend panel field key is invalid`、`frontend panel field keys must be unique` |
| `type` | `string` / `integer` / `number` / `boolean` | `frontend panel field type is invalid` |
| `title` / `description` / `placeholder` | 文本，长度上限 120 / 1000 / 240 字符 | 超长同样触发该字段的校验错误 |
| `required` | 布尔；只有字面量 `true` 生效 | 非 `true` 一律按 `false` 处理，不报错 |
| `default` | 必须与 `type` 精确匹配；敏感字段禁止出现 | `frontend panel default does not match <key> type` |
| `enum` | 标量数组，元素必须与 `type` 匹配 | `frontend panel enum must contain declared scalar values` |
| `minimum` / `maximum` | 只用于 `integer` / `number`，且 `minimum <= maximum` | `frontend panel minimum is numeric only`、`frontend panel maximum is numeric only`、`frontend panel minimum must not exceed maximum` |
| `format` | `uri` / `path` / `textarea` / `password`，只能用于 `string` | `frontend panel format supports only string controls`、`password panel format requires sensitive=true` |
| `sensitive` | 布尔，规则见 §3.5 | `frontend panel sensitive must be boolean`、`credential-shaped panel keys must be explicitly sensitive` |
| `visible_if` | 对象，允许 `key` / `equals` / `one_of` / `not_empty` / `all` / `any`，嵌套深度 ≤4 | `frontend field visible_if must be an object`、`frontend field visible_if contains an unknown property` 等 |

`visible_if` 只是渲染提示：宿主拿到的是校验后的对象（`all` / `any` 内部递归，
递归超过 4 层报错），后端不会据此隐藏字段或过滤提交值。

### 3.5 敏感字段：唯一允许输入密码的地方

`_SENSITIVE` 词表是 `api_key`、`apikey`、`token`、`password`、`secret`、
`credential`。判定方式是把字段 `key` 里的 `-` 换成 `_`、转小写后做子串匹配：

- 命中词表 ⇒ `sensitive` 必须为 `true`；
- 未命中 ⇒ `sensitive` 必须为 `false`。

两者不一致时报 `credential-shaped panel keys must be explicitly sensitive`。
因为做的是子串匹配，`max_tokens` 这类键也算凭据形状，只能按敏感字段写或改名。

`"sensitive": true` 之后还有三条硬约束（违反报
`sensitive panel fields require string password format and no default`）：

1. `type` 必须是 `string`；
2. `format` 必须是 `password`；
3. 不允许出现 `default` 键。

这些值只出现在本次 invoke 请求体里，不写入插件设置、不进入 `registry.json`；
GEOINT 宿主把敏感字段渲染成 `<input type="password" ... value="">`，并附提示
“仅本次提交使用，不会保存。”（`plugin-panel.js` 的 `panelControl()` /
`renderPanelField()`）。

## 4. 动作注册契约

每个 panel 的 `action` 都必须恰好对应一次
`runtime.register_ui_action(action_id, handler)`。加载结束时会比对集合，任一
情况都使整包加载失败（`_validate_ui_actions()`）：

| 情况 | 错误消息 |
|------|----------|
| 同一 action id 注册两次 | `plugin registered duplicate panel actions` |
| 有 panel 缺 handler，或注册了未声明的 action | `plugin panel actions do not match manifest` |
| handler 不可调用 | `plugin panel action handler is not callable` |

```python
from angelus.modules.plugin_module import (
    PluginRuntime,
    PluginUiActionRequest,
    PluginUiActionResult,
)


def lookup(request: PluginUiActionRequest) -> PluginUiActionResult:
    query = request.value("query", "")
    limit = request.value("limit", 10)
    if not isinstance(query, str) or not query.strip():
        return PluginUiActionResult("参数缺失", "query 不能为空。", "error")
    return PluginUiActionResult("查询完成", f"{query}（{limit} 条）", "success")


class Plugin:
    def setup(self, runtime: PluginRuntime) -> None:
        runtime.register_ui_action("lookup", lookup)


angelus_plugin = Plugin()
```

`teardown` 可选，不写时宿主注入空实现。字段校验全部在宿主侧完成（缺失
`required`、类型不符、越界、枚举外的值都被拒绝），handler 里只需处理业务语义。

## 5. 调用与错误语义

### 5.1 请求与响应

`POST /api/plugins/{plugin_id}/panels/{panel_id}/invoke` 的请求体是一个扁平
对象，键只能是该 panel 声明的字段：

```text
{"query": "mitre", "mode": "fuzzy", "limit": 5}
```

成功响应是 `{"title": ..., "content": ..., "tone": ...}`，`tone` ∈
`info` / `success` / `error`。宿主把 `title` / `content` 当纯文本渲染，所以插件
返回值无法注入 HTML。

### 5.2 提交值校验顺序

`_validate_fields()` 对面板使用 `defaults=True`（保存设置用的是 `defaults=False`），
顺序固定：

1. 未知键 → `unknown plugin fields: a, b`（排序后逗号分隔）；
2. 按 manifest 声明顺序遍历字段；缺失时：`required` 为真 → `missing required plugin field: <key>`，否则有 `default` 就补默认值并继续迭代；
3. 类型严格匹配（`bool` 不算 `integer`）→ `plugin field <key> has invalid type`；
4. `enum` → `plugin field <key> is not an allowed option`；
5. 下界 → `plugin field <key> is below its minimum`；
6. 上界 → `plugin field <key> exceeds its maximum`。

### 5.3 HTTP 状态与错误消息

| 情况 | 状态码 | `detail` |
|------|--------|----------|
| 请求体不是 JSON 对象 | 422 | `plugin panel values must be an object` |
| 插件不存在、未加载，或该 panel 未声明 | 404 | `active plugin panel not found` |
| 字段校验失败（§5.2 任一） | 422 | 对应消息原文 |
| action 未注册 | 422 | `plugin panel action is not registered` |
| handler 抛异常 | 422 | `plugin panel action failed: <Type>: <msg>` |
| handler 返回类型不对 | 422 | `plugin panel action must return PluginUiActionResult` |
| 成功 | 200 | `{"title", "content", "tone"}` |

panel 只有在插件处于已加载状态时才可调用；插件被卸载后同一请求直接返回 404。

### 5.4 状态投影

`GET /api/plugins/status` 里的 `panels` 由 `_panel_json()` 生成，只含
`id`、`title`、`description`、`submit_label`、`fields`——**不含 `action`**，
也不含 handler、文件路径等宿主内部信息。字段投影包含 `key`、`type`、`title`、
`description`、`required`、`default`、`enum`、`minimum`、`maximum`、`format`、
`placeholder`、`visible_if`、`sensitive`。

## 6. 宿主面：两套前端，能力不同

| 宿主 | 代码 | 面板怎么出现 | 是否加载插件自带脚本 |
|------|------|--------------|----------------------|
| 遗留工作台 | `frontend/static/plugins.js` | 渲染进 `.inspector-panels`，同时提供 `window.Angelus.{registerPanel, registerCommand, registerSettings}` 桥 | 会：`ENTRY_SCRIPTS = ["plugin.js"]`、`ENTRY_STYLES = ["plugin.css"]`，从 `/plugins/<name>/static/...` 取 |
| GEOINT | `frontend/geoint-src/components/plugin-panel.js`（`main.js` 第 29 行导入、第 178 行挂到 `[data-panel="plugins"]`） | `renderPluginPanels()`：只有 `state === "active"` 才渲染可提交表单，否则显示“插件加载后可提交”的说明 | 不会：面板完全靠 manifest 声明 + 文档化端点 |

GEOINT 侧的 `panelFields()` 会丢弃类型不受支持的字段声明（`PANEL_TYPES` 为
`string` / `integer` / `number` / `boolean`），而不是猜一个类型去提交——后端
本来也会以 422 拒绝，前端不做兜底转换。

## 7. 会被拒绝的写法

1. 在 `kind: "ui"` 或 `kind: "theme_pack"` 里写 `frontend.panels` → `frontend panels require a tool plugin entry`。
2. panel 里写 `handler`、`script`、`html`、`url` 之类键 → `frontend panel contains an unknown property`。
3. panel `id` 用大写、点号或过短（如 `a`）→ `frontend panel id is invalid`。
4. 两个 panel 复用同一个 `action` → `frontend panel actions must be unique`。
5. 字段 `key` 用大写或点号 → `frontend panel field key is invalid`。
6. 想给面板字段存 API Key 又给它 `default` → `sensitive panel fields require string password format and no default`。
7. 想让宿主执行插件自带 JS 来画面板 → 不存在这条路径；GEOINT 宿主只读 manifest 声明并调用 §5.3 的端点。
8. 期望按 `visible_if` 在服务端隐藏字段或过滤值 → 不存在，它只影响渲染提示。

## 8. 相关文档

- `docs/plugin-api.md` §2.5（`frontend.panels` 契约）、§4.4（UI action 强制校验）、§6（HTTP 端点）。
- `docs/plugin-guide.md` §6.2（`register_ui_action()` 写法）、§9.2（两套宿主界面差异）。
- 回归测试：`tests/test_plugin_manager.py` 的
  `test_declarative_panel_validates_inputs_and_invokes_registered_action`、
  `test_sensitive_panel_field_is_transient_and_settings_remain_secret_free`。
