# 边界

`GeoIntToolProvider` 拥有 Agent 意图的参数验证与受限 add/remove/reorder 转换；不直接访问文件路径。

`MapPresentationStore.put` 仍是有效地图文档的唯一写入路径，并验证资产绑定、组引用与 layer schema。

`agent_proposal` 继续属于提议机制，但不再由 GEOINT Agent 工具写入。

前端只读取 presentation；不必知道写入者是用户还是已授权 Agent。
