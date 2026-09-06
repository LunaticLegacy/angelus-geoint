# 边界

`assets.catalog` 只从 GDAL 元数据提取波段颜色解释与栅格尺寸；不决定样式。

`mapping.raster_style` 只根据元数据生成默认安全显示语义；不读取文件或改变持久化资产。

`MapPresentationStore` 继续保存用户渲染覆盖；不推断遥感波段含义。

`map-layer-sync` 仅执行已确定的 render contract；不猜测波段用途。
