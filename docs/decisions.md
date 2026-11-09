# Angelus 插件系统 — 架构决策记录（ADR）

> 状态：**历史决策 + 现状校正**。D1–D4 是最初 swarm 执行规格 §2 的默认值；代码已按实际实现演进，
> 与原始条目不一致的地方以「现状注记」为准。**现状注记是唯一权威**，原文条目仅保留决策背景。
> 下游 handoff 引用本文件时，必须引用现状注记，不要引用原文条目的假设。
> 安全边界的完整描述见 `docs/security.md`；本文件不重复定义权限语义。

---

## D1 插件加载模型：同进程 import

**原始决策**：**同进程 import**，命名空间 `angelus_plugins.<name>`；子进程隔离列为 v2 路线。

**现状注记（校正）**：
- 同进程 import 已落地：`angelus/modules/plugin_module/manager.py:565`（`_load`）→ `:594` `spec.loader.exec_module(module)`。
- 模块名并非点分 `angelus_plugins.<name>`，而是单段下划线名：
  `module_name = f"angelus_plugins_{manifest.name.replace('-', '_')}"`（`manager.py:580`）。
- 子进程隔离/sandbox **未实现**（仓库无相关代码），仍属 v2 路线，见 `docs/security.md` §9。
- **原文“权限校验（S10）是唯一边界”不成立**：仓库中不存在 `check_permission` / `require_permission`
  之类的 S10 校验函数。实际存在的是三道独立门禁：
  1. 显式确认：API 层 `confirm` 标志缺失即 `HTTPException(422)`（`angelus/api/plugins.py:102-103`、`:122-123`、`:146-147`）；
  2. 声明 + 授权：manifest 声明的权限未获授权且未传 `grant_permissions` 时，
     `ValueError("plugin permissions require explicit confirmation")`（`manager.py:271-273`；
     `grant_permissions` 参数见 `:249`）；
  3. manifest 静态校验：未知顶层字段直接拒绝（`angelus/modules/plugin_module/manifest.py:132-135`）。
- 运行期工具可见性由 ToolPolicy 会话门禁控制：`allows()` 要求分类已授权且工具在授权清单内
  （`angelus/modules/tool_module/tool_policy.py:62-83`）。完整边界表见 `docs/security.md` §7。

## D2 插件放置：与 workspace 并列的持久目录

**原始决策**：唯一的 `<app_data>/plugins`，与 `<app_data>/workspace` 并列；可通过环境变量 `ANGELUS_PLUGIN_DIR` 覆盖。

**现状注记（校正）**：
- 默认插件根：`state_root/plugins`；`ANGELUS_PLUGIN_DIR` 存在时取该值覆盖
  （`angelus/modules/plugin_module/store.py:37`；环境变量解析见 `angelus/core.py:50-53`）。
- 一个插件 home 内部拆成三类互不混淆的职责（`store.py:37-44`）：
  - `package_root = <home>/package`：只放被扫描的包目录（`store.py:38`）；
  - `legacy_package_root = <home>/packages`：旧布局，仍扫描但会告警（`store.py:42`；告警见 `manager.py:549-562`）；
  - `data_root = <home>/data`：插件运行期数据（`store.py:43`）；
  - `registry = <home>/registry.json`：注册记录与持久化设置（`store.py:44`）。
- **原文“`state_dir = <plugin_dir>/<name>/data`”不正确**。实际单插件数据目录是
  `<home>/data/<record.id>`（`manager.py:597`：`PluginRuntime(manifest, record.settings, str(self.store.data_root / record.id))`），
  即“数据根 + 插件持久化 ID”，不是“插件目录/名字/data”。
- 仓库内真实存在的插件包目录为 `plugins/angelus-deepseek-balance-v0.1.0`、`plugins/async-download`、
  `plugins/pofp-ctf`（仓库根 `plugins/` 实际列表）。

## D3 桌面版设置页：本期不纳入

**原始决策**：**本期不纳入**桌面设置 UI，仅保留后端 `GET /api/plugins` + 前端机制（`frontend/static/plugins.js` + `window.Angelus` 桥），桌面设置页留 v1.1。

**现状注记（校正）**：
- 后端端点已存在：`GET /api/plugins`（`angelus/api/plugins.py:50`），并有 `/status`（`:63`）、
  `POST /rescan`（`:76`）、`register`（`:90`）、`load`（`:110`）、`unload`（`:134`）、
  `settings`（`:176`）、`panels/{panel_id}/invoke`（`:215`）、`static`（`:262`）。
- 前端加载/注入机制已存在：`frontend/static/plugins.js:2`（“plugin frontend bridge & loader”），
  由 `frontend/static/app.js:22` 与 `frontend/static/main.js:11` 引入（`initPlugins`/`loadPlugins`/`unloadPlugin`）。
- **原文“CSP 自域放行”未实现**：`angelus/` 与 `frontend/` 内均无发送 `Content-Security-Policy`
  响应头的代码（全仓库匹配仅出现在 `.venv` 第三方依赖中），因此“CSP 自域放行”属未落地的说法。
- 桌面设置 UI（`frontend.settings` 注入页）**未实现**，与原文一致。

## D4 示例插件：网络搜索工具

**原始决策**：**网络搜索工具**，演示 `register_tool` + `register_hook`（搜索前后事件）全链路。

**现状注记（历史决策，已不成立）**：
- `PluginRuntime` 暴露的真实注册方法有四个，且**没有** `register_tool` 或 `register_hook`
  （`angelus/modules/plugin_module/models.py:372-418`）：
  `register_tool_provider`、`register_context_provider`、`register_ui_action`、`setting`。
- 仓库中不存在 hooks 事件注册机制（无 `register_hook`、无 `HOOK_EVENTS`），
  因此“搜索前后事件”的 hook 演示**无从实现**。
- 交付位置 `plugins/example-tool/` **不存在**；仓库真实插件是
  `plugins/angelus-deepseek-balance-v0.1.0`、`plugins/async-download`、`plugins/pofp-ctf`。
- 结论：D4 保留为**历史决策**记录，不再作为实现目标；若需“示例插件”，以现有三个真实插件为准。

---

## 决策变更流程

若用户后续推翻任一决策，只改本文件对应条目（含现状注记），并同步更新
`docs/plugin-api.md` 中受影响的契约段落；下游 handoff 引用本文件现状注记，无需逐单元重发。
