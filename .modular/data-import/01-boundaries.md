# 模块边界

| 模块（拟定文件） | 唯一职责及所有权 | 公开边界 | 禁止依赖 / 替换测试 |
|---|---|---|---|
| import-contracts (`geoint/imports/models.py`) | 严格请求、任务快照、候选图层、错误及限额类型 | Pydantic DTO | 不依赖 HTTP/磁盘/UI；可单独验证 |
| import-storage (`geoint/imports/storage.py`) | 会话受管原件、临时文件、manifest、字节计数/hash、原子更新 | create/write_chunk/seal/read_snapshot/update/cleanup | 不注册资产、不读任意路径；换存储实现不改 UI/流程 |
| import-inspector (`geoint/imports/inspector.py`) | 安全解包、驱动白名单、数据集与 CRS/字段候选检查 | inspect(受管输入句柄)→Inspection | 不写 catalog、地图，不启网络；独立恶意文件夹具测试 |
| import-preparer (`geoint/imports/preparer.py`) | 按显式配置生成并验证可显示派生物 | prepare(候选ID,配置)→PreparedRepresentations | 不决定权限/发布；不用 shell/用户命令；可替换 GIS 引擎 |
| import-service (`geoint/imports/service.py`) | 导入状态机、队列、取消、恢复、发布协调 | create/seal/configure/commit/cancel/get/list | 不拥有资产事实或 MapDocument 副本；依赖注入叶模块 |
| import-api (`api/geoint_imports.py`) | HTTP 编解码、流式请求限额、错误映射 | session-scoped REST | 不创建第二份 service/store、不运行 GIS 转换 |
| file-drop-target (`geoint-src/components/file-drop-target.js`) | 文件拖放反馈和 File[] 意图 | mount(element,onFiles)→dispose | 不知道会话/网络/地图引擎；不拦截标签拖动 |
| data-import-panel (`components/data-import/`) | 来源列表/预检/CRS/CSV 映射/进度组件及本地草稿 | render(snapshot), onIntent | 无 fetch/OpenLayers/路径；移动同一组件不重启任务 |
| import-controller (`controllers/import-controller.js`) | File 生命周期、上传传输、任务轮询、会话切换隔离 | acceptFiles/confirm/cancel/resume/dispose | 不解析 GIS、不直接添加 OL 图层；可用假 API/假 view 测试 |
| import-client (`import-client.js`) | 原始字节上传及传输进度、REST DTO | upload(file,signal,onProgress), request | 不拥有业务状态；不复用会给 FormData 强加 JSON 头的旧 api 包装 |
| desktop-import-bridge (`src-tauri/src/main.rs` + `native-import-bridge.js`) | 桌面拖入路径的原生接收、受管字节流上传、进度/预检事件桥接 | selected-session command, `geoint://native-import` event | 不向 JS 暴露路径、不授予 FS API；浏览器仍只走 `File[]` |

复用并扩展：catalog 拥有唯一资产 ID、会话绑定和公开表示；presentation 拥有地图文档和用户添加图层记录；map-core 只消费服务端表示。业务不进入通用 Dock 或 Angelus Agent。

应用装配新增 `geoint/runtime.py`：每个 core 一套 GEOINT 实例；HTTP 与工具共享注入。现有 service 保留业务 facade；移除该 runtime 只影响 GEOINT，而非会话/连接器/运行能力。

会话生命周期 guard 是已有 session 所有权的内部协作边界，不是新 Session：发布与删除共用短期会话锁；删除时阻止后续导入发布。需要给现有 SessionService 删除路径增加内部 guard 协作，不改外部契约。
