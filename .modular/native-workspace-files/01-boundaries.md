# 模块边界

| 模块 | 所有权 | 公共契约 | 禁止事项 |
|---|---|---|---|
| workspace-ui | 会话卡片中的已投影工作空间路径及按钮意图 | `renderSessions` / `showSession` | 不启动 OS 程序、不保存路径 |
| native-import-bridge | 是否存在桌面能力及无路径的选择/打开意图 | `chooseFiles()` / `openWorkspace()` | 不持有文件路径、不自行上传 |
| Tauri desktop bridge | 原生文件选择、当前受选会话授权、默认文件管理器调用、原生路径到既有 `desktop_import` 的转换 | 两个受限 command 与既有事件 | 不把路径返回给 JS；不允许任意路径 command |
| import-controller | 浏览器 `File[]` 上传降级 | `acceptFiles()` | 不感知桌面路径 |

删除测试：删除 desktop bridge 只使桌面原生选择/打开失效；浏览器导入与会话路径显示仍可用。
