# 契约

- `choose_geoint_import_files()`：不接收参数；仅在 Rust 已记录当前 session 时显示多选原生对话框。取消返回 `false`；选择 `.shp` 时，桌面端自动补入同目录同名的 `.shx`、`.dbf` 及存在的 `.prj`、`.cpg`，随后后台调用既有 `desktop_import`，只经 `geoint://native-import` 发布无路径进度与结果。
- `open_geoint_workspace()`：不接收路径；从 workspace catalog 取得当前受选 session 的 `project_path`，用系统默认文件管理器打开。JS 仅得到成功状态。
- native bridge：仅当 `__TAURI__` bridge 可用才调用上述命令；否则返回 `false`，组件回退到既有浏览器文件选择。
- session list projection 已有 `project_path`；UI 将它作为只读文本渲染，不作为新的后端契约。
