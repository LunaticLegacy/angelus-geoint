# 契约

新建 GeoJSON 图层的 `render` 默认值为：

```json
{
  "kind": "vector",
  "stroke_color": "#3f82e8",
  "fill_color": "#3f82e8",
  "fill_opacity": 0.11
}
```

`Layer.render.kind == "vector"` 时只允许 `kind`、`stroke_color`、`fill_color` 和 `fill_opacity`。颜色必须是 `#RRGGBB`；透明度是有限数值且在 `[0, 1]` 内。旧的 `{kind:"vector", mode:"single"}` 记录继续可读，并在浏览器端回退到默认值。

`layer-panel` 发送 `{type:"patch", id, patch:{render}}`。既有 `main -> PUT map-presentation` 的完整文档写入继续是唯一写路径。

输入控件同时发送暂态 `preview-vector-style` 意图；`main` 只调用地图
适配器更新当前 OpenLayers 图层，不发请求、不修改地图文档。“应用矢量样式”
仍发送上述 `patch`，作为持久化确认。

矢量编辑器保留进入卡片时的已持久化样式快照。草稿与快照不同时显示
“已预览，尚未保存”；“还原”只将该卡片与对应 OpenLayers 图层恢复为快照，
不请求或刷新其他图层；“保存矢量样式”才提交 `patch`。

`geoint_manage_map_layers(operation="set_vector_style", layer_id,
stroke_color?, fill_color?, fill_opacity?)` 只作用于当前会话的 GeoJSON
图层。省略的字段保持原值；提供的值经同一 `Layer.render` 校验后写入。
