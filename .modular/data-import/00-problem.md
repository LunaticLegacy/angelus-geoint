# 外部数据导入：受控上传与地图发布

状态：已完成 GeoJSON 与 GeoTIFF/COG 的可发布 MVP。其余计划格式保持明确禁用，不能被 UI 或 Capabilities 误报为支持。

目标：浏览器拖放/选择文件 → 会话内暂存 → 格式/图层/CRS 预检 → 用户确认 → 派生可渲染副本 → catalog 注册绑定 → MapDocument 用户图层发布。刷新可恢复，错误不伪装为空图层，保留原件。

首版格式：GeoJSON、GeoPackage（选择矢量子图层）、Shapefile ZIP、GeoTIFF/COG、CSV 点。首版不做目录拖放、裸 SHP 多文件配对、GPKG 栅格、远程 URL 下载、FileGDB、地理编码、任意 SQL、任意 GDAL 参数、上传断点续传、超大矢量瓦片服务。已有授权目录扫描入口保留，但不接受用户随意填宿主机路径。

## 已核实的事实

- `angelus/geoint/catalog/service.py`: 现有扫描/注册/绑定；`bound_path` 只认识外部目录 grant，尚无 session-owned 文件定位契约。注册远程资产也不保证存在可渲染本地副本。元数据扫描不是严格格式验证，不能作为导入安全边界。
- `angelus/api/geoint.py`: GeoJSON/GeoTIFF 可直接读取；XYZ 资产瓦片返回 501，非 GeoJSON 属性与栅格 identify 未实现完整能力。不能在本功能中声称已经支持。
- API 模块级 service 使用 cwd state；工具 provider 使用 core.state_root 且独立构造 catalog/presentation。新任务必须统一 GEOINT 依赖注入和持久化锁，否则新导入可能被不同实例覆盖。
- `presentation.py`: put 整体替换覆盖文档、非原子写；agent_override 直接返回 Agent 层集合。必须补原子添加/幂等提交，以及用户独立添加图层的集合合并契约。
- `frontend/geoint-src/map.js`: 向量整份读取且默认 GeoJSON→3857；现有文件拖放未接入，dock 接收 text/plain 的标签拖动。导入结果必须有明确可用表示且限制大小。
- `crs.py`: 当前分析约定为 EPSG:4326 / EPSG:32662；不为导入擅自改写。显示投影 3857、源 CRS、分析 CRS 必须区分。
- Workspace.state_path 属 Angelus；project_path 属用户。`SessionService.delete` 删除 state_path。上传原件/派生物只能写前者，不写用户工程/外接盘。

索引路径：根 → angelus → geoint / api / modules(application,workspace)；根 → frontend；根 → tests。索引有历史描述，以上结论以叶文件为准，不在设计阶段批量重建索引。

约束：Angelus 既有 HTTP 路径/请求/响应/Agent 所有权不变；首版单服务进程，有限并发子进程执行 GIS 预检转换；GDAL/PROJ 能力不足时明确拒绝该格式，不静默降级为成功。
