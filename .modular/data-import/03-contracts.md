# HTTP 和服务契约（拟定）

所有入口在 `/api/geoint/sessions/{session_id}/imports`，验证真实 Workspace 存在以及任务归属；未知/跨会话任务统一404。沿用本地工作台信任边界，session_id 本身不是多租户登录鉴权。

| 方法/后缀 | 输入 | 输出 |
|---|---|---|
| GET `/capabilities` | 无 | 格式/驱动可用性、支持的 CRS 处理、服务器限额 |
| POST 根 | `{files:[{name,size_bytes}], client_request_id}`，不含路径 | 201 `{import_id,session_id,files:[{file_id,...}],status,revision}` |
| PUT `/{id}/files/{file_id}` | application/octet-stream 完整流；非 multipart | 已接收字节数、服务端 SHA256；重复相同上传幂等，不同内容409 |
| POST `/{id}/inspect` | `{expected_revision}` | 202 任务快照，异步预检 |
| GET 根 / `/{id}` | 有界分页 / 无 | 本会话任务列表 / 最新状态及候选 |
| POST `/{id}/commit` | 严格配置见下，`expected_revision` | 202；同任务同规范化配置重试幂等，不同配置/版本冲突409 |
| POST `/{id}/cancel` | `{expected_revision}` | 快照；已发布不可取消，不等于删除资产 |

选择文件名只作显示，生成 file_id 存储，拒绝路径字符/控制字符，文件名不用于构造宿主路径。只有 service 可获得 internal path，API/Agent 只能得到 ID。

候选：`{dataset_id,file_id,name,format,geometry_types,fields:[{name,type}],bands,source_crs:{authority,wkt,origin,status},extent:{bbox,crs},issues,renderability}`。所有统计有界，unknown 不能写成0；栅格统计可 deferred。任务错误为 `{code,message,retryable,dataset_id?,details?}`，不回传宿主路径/堆栈。

commit：`{expected_revision,datasets:[{dataset_id,assigned_crs?:{authority},csv?:{x_field,y_field,encoding,delimiter,invalid_rows:"reject"|"skip"},raster?:{data_kind:"categorical"|"continuous",resampling:"nearest"|"bilinear"},title?}],add_to_map:true}`。字段从预检候选选取，CRS 从受控本地数据库识别，严禁任意 PROJ pipeline、SQL、过滤表达式、VRT、URL和可执行参数。服务器决定输出路径/格式/source URL。

completed：`{status,assets:[{asset_id,dataset_id}],layers:[{layer_id,asset_id}],map_revision,warnings}`。前端随后重新 GET map-presentation，仍由现有 factory 渲染；不能用上传的 Blob URL 绕过权限直接加图层。定位按钮只用已转换的 extent，默认导入不强制改变已有视角。

## 现有领域扩展

- catalog `register_managed_batch(session_id, import_id, entries)`：仅服务内使用，确定性 asset_id、managed locator、原件/显示表示/hash/lineage；不伪造用户 directory grant。`bound_path(..., representation="display")` 保持受控读取；analysis 显式请求 original，公开 DTO 不含内部 locator。
- presentation `append_user_layers(session_id, operation_id, layers)`：加锁、原子写、保留最新视图/分组/样式/Agent 提议；operation_id 去重，不回放覆盖用户后续编辑。revision 用于新操作并发控制，旧 PUT 接口保持兼容并共享锁。
- authority 策略作用于相同 ID 的冲突字段；用户新建且 Agent 从未提议的层不因 agent_override 被丢弃。该集合语义修正是显式迁移点，必须单独测试全部三种策略。导入不修改当前策略，不把用户操作伪装成 Agent 提议。
- catalog 批量读改写全局锁；presentation 每会话锁；共同生命周期 guard→catalog→presentation 的固定加锁顺序。首版单 API 进程，GIS 子进程只读原件/写任务派生目录，不改这些 stores。
