# 契约

`geoint_propose_map_presentation` 不再 materialize 或注册。

`geoint_manage_map_layers` 的 `add/remove/reorder` 参数保持兼容；
`set_vector_style(layer_id, stroke_color?, fill_color?, fill_opacity?)` 仅更新
当前会话 GeoJSON 图层的受限矢量显示字段。成功时调用
`MapPresentationStore.put`，返回 `{operation, map_presentation, effective_layers, note}`；note 明示已直接修改当前会话地图、原始资产未删除。

add 仅接受当前会话已绑定的 GeoJSON/GeoTIFF asset ID；remove/reorder 和
set_vector_style 仅接受当前 effective 文档的 layer IDs；set_vector_style
拒绝栅格图层和任意 render JSON。全部操作以 source 为空的可编辑文档进入 Store。
