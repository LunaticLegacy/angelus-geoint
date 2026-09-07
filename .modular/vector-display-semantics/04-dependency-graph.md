# 依赖图

`mapping.layers -> mapping.vector_style`

`mapping.document -> vector render contract`

`main -> layer-panel`

`map-layer-sync -> OpenLayers Style`

禁止：`layer-panel -> fetch`、`map-layer-sync -> map-presentation API`、`mapping.document -> OpenLayers`。
