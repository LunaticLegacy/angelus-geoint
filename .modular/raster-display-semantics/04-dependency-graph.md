# 依赖图

`assets.catalog -> GDAL metadata`

`mapping.raster_style -> raster metadata contract`

`map-presentation API -> mapping.raster_style`

禁止：`mapping.raster_style -> filesystem`、`map-layer-sync -> GDAL`。
