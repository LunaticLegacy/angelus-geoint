# 实施顺序

1. 用 `analysis`、`assets`、`mapping`、`agent`、`runtime` 语义包承接全部现有顶层实现，更新内部与应用层导入，并建立 facade。
2. 将当前 `imports` 吸收进正式 `ingestion` 包，保留对外 `ImportService` 名称。
3. 新增 `ingestion.shapefile`：验证包、使用 OGR 检查并转成受管 GeoJSON。
4. 使 `ImportService` 按数据集包而非按文件迭代；保持 GeoJSON/GeoTIFF 兼容。
5. 更新 API/前端格式能力与选择器，补充单元测试和包导入 smoke test。
6. 更新 GEOINT 索引，并以 `refactor` 与 `feat` 两个原子提交交付。
