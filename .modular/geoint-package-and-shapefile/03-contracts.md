# 公开契约与 facade

外部应用的稳定导入形式为：

```python
from angelus.geoint import GeoIntRuntime, GeoIntService, GeoAssetCatalog
from angelus.geoint import ImportService, MapPresentationStore, GeoIntToolProvider
```

对应领域函数也从 facade 暴露：`drought_score`、`drought_level`、`crs_convention`、`map_representation`、`layer_record`、`default_raster_render`、`prepare_web_raster`、`download_public_dataset`、`BasemapStore`、`XYZConfig`。

公共导入不暴露存储路径、GDAL dataset、上传 sink 或私有 manifest。格式能力由 `ImportService.capabilities()` 公开；上传声明允许的扩展名由 `ingestion.models` 单点定义。

SHP 候选项使用一个 `dataset_id`，并携带 `file_ids`（而非单一 `file_id`）。准备显示副本接受候选包上下文，其他格式仍可走单文件快捷路径。

`convert_shapefile_to_geojson` 使用受控、临时物化的 `.shp` **路径**作为
GDAL `VectorTranslate` 输入；不将 OGR 的 SWIG `DataSource` 句柄跨 GDAL
Python 绑定边界传递。这个路径只在转换上下文中存在，绝不返回给 API 或浏览器。

CI 契约：受支持的 Python 3.12 与 3.14 都必须运行含 GEOINT extra 的测试集。
每个 Linux 测试环境先安装系统 `gdal-bin` / `libgdal-dev`，再以
`gdal-config --version` 安装同版本的 GDAL Python 绑定；不得以未安装 GDAL 的
基础测试替代该验证。
