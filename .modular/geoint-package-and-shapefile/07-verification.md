# 验证记录

已完成：

- `python -m compileall -q angelus/geoint angelus/api angelus/core.py`
- facade smoke import：`GeoIntRuntime`、`GeoIntService`、`GeoAssetCatalog`、`ImportService`、`MapPresentationStore`、`GeoIntToolProvider`
- `python -m unittest tests.test_geoint_shapefile`：3 项通过（含 GDAL/OGR 创建、检查、转换完整 SHP 包）
- `npm run test:geoint`：通过
- `npm run build:geoint`：通过；仅保留既有的 Vite 大 chunk 与 Node module-type 警告
- `git diff --check`：通过

待本次 CI 配置变更验证：Python 3.12 和 3.14 矩阵均安装
`GDAL==$(gdal-config --version)` 后运行完整测试集。该依赖只属于 Linux 测试
运行时，不改变 GEOINT facade 或其他模块依赖边界。

环境限制：完整 API import 测试未运行，因为当前解释器环境未安装 `fastapi`；这不是 GEOINT 包重构的导入错误，GEOINT facade 与所有语义子包的 smoke import 已通过。
