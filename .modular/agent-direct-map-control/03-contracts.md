# 契约

`geoint_propose_map_presentation` 不再 materialize 或注册。

`geoint_manage_map_layers` 的 `add/remove/reorder` 参数保持兼容，但成功时调用 `MapPresentationStore.put`，返回 `{operation, map_presentation, effective_layers, note}`；note 明示已直接修改当前会话地图、原始资产未删除。

add 仅接受当前会话已绑定的 GeoJSON/GeoTIFF asset ID；remove/reorder 仅接受当前 effective 文档的 layer IDs；全部操作以 source 为空的可编辑文档进入 Store。
