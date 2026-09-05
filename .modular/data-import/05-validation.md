# 架构门禁

Architecture: PASS。Implementation: PARTIAL PASS（GeoJSON、GeoTIFF/COG MVP）。

已验证的实现边界：浏览器仅上传 `File` 字节；`ImportStorage` 唯一拥有暂存和 manifest；预检只处理白名单格式；`ImportService` 通过 catalog 注册受管副本、通过 presentation 原子追加用户层；前端只刷新 MapDocument。API 与 Agent 都不接触宿主机路径。

桌面壳拖入由 Tauri 主窗口 `WindowEvent::DragDrop` 原生事件接收：路径只在 Rust 壳内使用并以 HTTP 字节流交给 loopback API；WebView 仅可调用会话同步命令、订阅无路径的进度/预检事件。能力文件限定为 `http://127.0.0.1:*` 的 main 窗口，未启用文件系统、对话框或 shell 权限。
桌面地图拖入不再回退到 DOM `FileList` 上传，避免某些 WebView 同时触发原生与 DOM 事件而重复创建任务；浏览器地图拖入和所有平台的“选择文件”按钮仍使用前端 controller。

尚未通过验收、并在 Capabilities 中禁用：Shapefile ZIP、GeoPackage、CSV、后台 GIS worker/队列、取消/TTL 清理、跨进程发布锁和真实 COG 合规验证。它们仍需按 I2–I6 的原计划单独完成，不属于本次 MVP 的承诺。

反向审查：状态所有权唯一、图无环、UI 不读磁盘/不操作 OpenLayers、HTTP 不拥有任务状态、catalog 不拥有向导状态、session 仍由 Angelus 拥有。存储/解析/转换/发布可独立夹具测试；替换 UI 不改服务，替换 GIS 驱动不改 API。

## 安全与资源约束（首版默认，可由服务器收紧）

- 每任务最多16文件，单文件512 MiB，合计1 GiB；会话受管导入占用默认5 GiB（原件+解包+派生+正在上传预留）；先预留额度再流式写，实际字节计数执行限额，不能只相信 Content-Length。
- ZIP 最多256条目、解压合计1 GiB、压缩比上限100:1；逐条/逐块核验，拒绝绝对路径、..、符号/硬链接、大小写重名覆盖、加密或嵌套包。只接受 SHP sidecars 白名单且同 stem 至少 shp/shx/dbf；缺 prj进入 CRS确认，不自动猜测；cpg按明确支持编码处理。
- 驱动白名单与内容检查；拒绝 VRT/网络VSI/外部链接，GPKG不加载SQLite扩展/用户SQL；GIS worker禁网、受限目录、进程内存/CPU/超时限额（默认2 GiB/120s CPU/300s墙钟，准备大型栅格可由服务器增加）。不能仅依赖线程超时去声称已取消计算。平台无法落实 worker约束时禁用相应格式并报告原因。
- 同时最多2个 GIS worker、每会话最多1个活动处理任务，队列有界；只做抽样元数据，不自动全量计算栅格统计。显示 GeoJSON 默认最多50k要素及20 MiB，超限返回表示准备失败，不静默截断冒充全量数据；更大矢量切片另期做。
- 上传原件和manifest模式0600、受管目录0700；SHA256防传输/后续篡改；GDAL错误脱敏。下载/Range/属性端点均先校验绑定，路径和外部URL不进前端。
- 未确认暂存24h后可清理，仅清理本模块 manifest 指向的未发布受管目录；completed 原件/派生物不按TTL删除。断开浏览器不等于取消；显式取消和会话删除须终止 worker并释放预留。
- 发布/会话删除并发需要共同 lifecycle guard，不能只“前后查一次session”。内部 guard扩展不改删除API；会话删除完成后不能创建目录或发布幽灵资产。清理全局catalog中的已删会话记录时只处理托管记录，不删除用户原件/其他会话绑定。

## 主要风险及实施门禁

1. GEOINT 多实例/cwd路径与非原子store是实际缺口：先统一依赖和锁，之后才实现上传发布。
2. 当前识别为TIFF不等于COG可显示：验收须验证真实206 Range、CRS、NoData以及实际OL呈现，不只看Accept-Ranges头。
3. 所有生产支持格式必须通过缺依赖/恶意文件/超限测试；无GDAL时Capabilities显式降级。
4. 不改变现有分析EPSG:32662约定，也不宣称Web Mercator显示产物适合面积统计。
5. 单进程限制须进入启动/部署文档；多Uvicorn worker需要跨进程事务与队列，首版不宣称支持。

各实施任务需再次对照代码验证；不以本PASS跳过功能/安全/浏览器验收。
