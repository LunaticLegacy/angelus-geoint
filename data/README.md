# 本地 GEOINT 指标数据

风险研判只从本目录及其子目录读取已登记的数据文件。当前离线闭环接受
GeoJSON `FeatureCollection`；每个空间单元必须具有几何对象，并在
`properties` 中提供下列已标准化的同期异常值：

GeoJSON 坐标必须为 WGS84 经纬度（EPSG:4326）。后续栅格土地利用/遥感
数据进入处理链前统一转换到 WGS 84 / Plate Carrée（EPSG:32662）；土地利用
等离散分类使用最近邻重采样。

```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "id": "unit-001",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[109.65, 34.76], [109.66, 34.76], [109.66, 34.77], [109.65, 34.77], [109.65, 34.76]]]
    },
    "properties": {
      "ndvi_anomaly": -0.21,
      "rainfall_anomaly": -0.38,
      "soil_moisture_anomaly": -0.18,
      "confidence": 0.86,
      "observed_at": "2026-08-20",
      "source": "sentinel-chirps-local"
    }
  }]
}
```

`ndvi_anomaly`、`rainfall_anomaly` 与 `soil_moisture_anomaly` 为必填数值；
负值表示较同期偏低。`confidence` 可选，范围为 0–1。登记后系统记录
文件 SHA-256；修改原文件后必须重新登记，避免结果无法追溯。

这是离线指标输入契约，不是合成样例数据。请不要将演示数据或未经质检的
数值作为比赛结论来源。
