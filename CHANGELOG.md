# Changelog

本文件记录 Angelus 的面向用户发行说明，采用
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构。

## [Unreleased]

### Added

- `docs/llmfetcher-upgrade.md`：记录 llmfetcher 上下文从 `LLMContext` 迁移到
  `ContextItem` 判别联合后，angelus 侧的适配范围、旧 checkpoint 兼容策略与迁移步骤。
- `scripts/migrate_context_to_v2.py`：把旧版内联 `context.json` checkpoint 单向迁移为
  v2 SQLite 指针。默认干跑，只有 `--apply` 才写入并保留 `context.json.legacy.bak`；
  存在无法迁移的 checkpoint 时返回非零退出码，可直接用作部署门禁。
- `.gitattributes`：`frontend/static/geoint-dist/**` 标记为生成物并关闭行尾转换，
  `src-tauri/Cargo.lock`、`*.patch` 按文本处理，图片与视频按二进制处理；
  `.gitignore` 补齐构建与测试生成物规则。
- 移除仓库根目录的 `flag.txt`，改由测试在运行时生成对应 fixture。

### Changed

- llmfetcher 子模块升级到 `e5c03e0`（`v0.6.0-8`），对应 `pyproject.toml` 约束
  `llmfetcher>=0.6.0,<0.7.0`；CI 的 `test` job 会在安装依赖前记录子模块版本，并断言
  它满足该约束且工作区指针与 `HEAD` 记录一致（`.github/workflows/ci.yml`）。
- **破坏性变更**：适配 llmfetcher 新的 `ContextItem` 判别联合上下文 API
  （`UserContextItem` / `AssistantContextItem`），checkpoint 持久化从单文件内联 JSON
  改为 SQLite 指针 + sidecar 数据库。
- 上下文读取增加对旧版内联 JSON checkpoint 的兼容，未迁移的历史不会被静默读成空；
  写入方向只写 v2 格式。

## [0.5.0-rc.1] - 2026-09-02

### Fixed

- 修正 SIGINT 竞态回归测试：当工作线程在强制停止请求后立即退出时，测试现在
  校验持久化的停止请求事实，并接受合法的即时 `STOPPED` 终态。

## [0.5.0-rc.0] - 2026-09-02

这是 `0.5.0` 的发布候选版。Angelus 与 llmfetcher 独立版本化；本版本要求
`llmfetcher >=0.4.0,<0.5.0`。

### Added

- Session 作为唯一运行时所有者的控制台 API：任务计划、Agent 图、Trace、用量
  与上下文图均可在重启后恢复。
- 统一的工具注册、权限和 Provider 物化链路；Agent 按有效 Session 策略获得
  当前可用工具。
- 声明式插件功能面板和类型化非敏感插件设置。面板 action 由宿主调用并安全地
  返回文本结果。
- External Agent Hub 的发现、协议适配与外部上下文交换基础设施。
- GZCTF v1 插件迁移：11 个命名空间 Agent 工具、私有 Cookie/下载/批处理状态，
  以及一次性密码登录面板。

### Changed

- 执行、事件流、停止控制、图编辑和右侧控制台统一以 `session_id` 为身份；移除
  workspace-run 兼容执行路径。
- 上下文恢复支持按页读取最近记录，避免恢复窗口时全量读写。
- LLM 输出使用流式 Markdown 渲染，并且只在阅读位置仍处于底部时自动跟随滚动。
- 插件入口以受控 Provider 发布工具；相对模块导入会在插件卸载时一并清理。

### Security

- 密码等敏感字段禁止进入插件持久化设置。声明式面板仅可通过
  `sensitive: true` 与 `format: "password"` 接收一次性密码，且不允许默认值。
- GZCTF Cookie、附件和自动化运行数据均保存在 Angelus 插件私有状态目录，插件
  源码目录不再承载运行时凭据。

### Upgrade notes

- 旧 GZCTF 插件需要在设置中重新扫描并重新加载。保存 `base_url` 与 `username`
  后，再通过“登录 GZCTF”面板建立 Cookie 会话；密码不会迁移或保存。
- 旧的插件 manifest 字段 `entry_type`、`tools`、`commands` 和
  `settings_actions` 不再被 v1 运行时接受，应迁移为 Provider、
  `settings_schema` 与 `frontend.panels`。

[0.5.0-rc.0]: https://github.com/LunaticLegacy/Angelus/releases/tag/v0.5.0-rc.0
[0.5.0-rc.1]: https://github.com/LunaticLegacy/Angelus/releases/tag/v0.5.0-rc.1
