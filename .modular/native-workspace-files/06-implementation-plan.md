# 实施计划

1. 用 `tauri-plugin-dialog` 在 Rust shell 中添加原生多文件选择 command，并复用 `desktop_import`。
2. 添加仅打开当前受选 workspace 的 command；按平台调用默认文件管理器。
3. 给 desktop capability 添加两条 command permission。
4. 扩展 JS bridge、导入组件和会话卡片；浏览器保留 FileList 降级。
5. 为 bridge 写契约测试，构建 Vite、运行 JS 测试与离线 Cargo 检查。
6. 浏览器降级路径在上传前验证已选择的 Shapefile bundle；因浏览器不具备目录枚举权限，不猜测或伪造未选择的旁车文件。
