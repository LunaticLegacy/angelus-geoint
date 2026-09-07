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
