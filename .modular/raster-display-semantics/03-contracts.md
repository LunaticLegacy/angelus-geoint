# 契约

栅格 metadata 的每个 band 可提供 `color_interpretation`，并可提供 `raster_size: [width, height]`。

`default_raster_render(metadata)` 仅当第 1–3 波段的颜色解释依次为 Red、Green、Blue 时返回 `mode: rgb` 和三波段；否则返回 `mode: single_band`、`bands: [1]`、`interpolate: false`。

显式传入的 render 字段仍优先于默认值。
