# 状态、坐标与失败语义

任务绑定创建时的 session_id，不随顶部选择器改变。切换会话不会把旧任务结果加进新会话，也不会自动取消服务器任务。未选会话时拒绝上传并提示选择；不自动建会话。File 对象只在上传期间由 controller 持有，不放 localStorage。

状态：receiving → inspecting → awaiting_confirmation → preparing → publishing → completed。
receiving/inspecting/awaiting_confirmation/preparing 可 cancelled/failed；进程重启把未完成上传标 interrupted（重传），中断转换可从完整原件重试，publishing 按日志幂等续完或保留 publish_failed 等待重试。completed 只表示全部选定层已注册、绑定、加入地图文档；不能仅上传/转换完成就置 completed。

同一任务选择多个子图层为一个发布批次。所有派生物验证通过后才提交 catalog 批次；地图批量追加一次。跨两个文件不宣称 ACID：先记 publishing intent/固定ID，再 catalog 幂等注册绑定，再 presentation 幂等追加，再 completed。中断可能存在“已入目录但未上图”，状态明确展示，恢复时重试，不重建/重复图层，不覆盖用户随后编辑。取消 publishing 返回 409，防止一边清理一边发布。发布最终失败保留原件和已发布资产用于修复，绝不自动删除已有用户资产。

## CRS

- source_crs：原件嵌入 CRS 或用户明确指定的解释；同时记录 origin=embedded/format_default/user_assigned 和原始 WKT/authority。
- GeoJSON 按 RFC7946 经纬顺序 lon,lat；非标准旧 CRS/异常范围要求确认或拒绝，不能只看扩展名硬写 4326。
- 缺失 CRS 必须停在 awaiting_confirmation；CGCS2000 等不是“选中后自动变成 WGS84”。有 CRS 时首版不开放随意覆盖；冲突返回提示。
- CSV 先选字段/编码/分隔符，再声明坐标基准；经纬度点首版仅 WGS84，可识别其他基准但拒绝未实现偏移转换。非数值/越界行显示计数和少量行号；默认失败，明确选择 skip_invalid 才跳过并记录；全部无效失败。
- 向量显示副本为 EPSG:4326 GeoJSON，OpenLayers 转显示 3857；GPKG 每个选中矢量层、ZIP 每个 shp 都是独立候选。
- 栅格保留原件；首版生成/验证 EPSG:3857 COG 显示副本，只有已兼容且通过 COG 验证才可复用受管原件。分类必须 nearest，连续值用户可选 nearest/bilinear；NoData、波段、extent、转换参数进入 lineage。
- 原数据的科学分析 CRS 不跟随底图或显示副本改变；不可用显示副本冒充分析原件。PROJ 缺转换格网/只能 ballpark 时拒绝自动精密转换并反馈；不联网补文件。
- 超出3857有效纬度、跨日期变更线的范围不做无提示裁剪；首版提示不可显示或需要明确预处理。

不伪造属性/identify/切片能力：catalog 按生成物实际能力声明；栅格首版显示真实波段元数据，不声称已有像元识别。
