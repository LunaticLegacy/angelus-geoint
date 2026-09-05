# 底图与定位

## 通用地图源管理

宽面板显示「来源列表 + 配置详情」，窄面板自动改为单栏，断点依据组件宽度。查看来源与当前显示来源独立，点击「用作底图」才切换。选择需要凭据的预设才显示「来源凭据」，不再固定展示天地图设置。

「添加地图源」提供公开 HTTPS XYZ 表单，已保存的自定义源可原地编辑；高级 JSON 导入仍保留。天地图是内置预设。其他提供者只要满足公开 XYZ 契约即可配置，不代表已支持其私有鉴权、专用 SDK 或特殊网格。

自定义配置新增 `geographic_crs: "EPSG:4326"` 和 `tile_grid: "XYZ"`，旧配置按既有约定补默认值。当前只支持 WGS84 对齐、EPSG:3857、256 像素左上原点 XYZ；不支持的声明在后端拒绝。这些声明不是对源数据的自动检测或转换。

## 坐标说明

- 地理坐标系描述地球基准及经纬度；投影坐标系描述平面坐标；瓦片网格还规定原点、分辨率、尺寸及编号方向。三者不能混为一谈。
- OSM 的地理数据使用 WGS84，标准瓦片使用 Web Mercator EPSG:3857。
- 天地图 `_w` 是墨卡托瓦片，当前适配器采用 EPSG:3857；`_c` 是经纬度瓦片，需要不同网格，当前未接入。不能仅由后缀断定原始数据基准；例如[天地图陕西说明](https://shaanxi.tianditu.gov.cn/docHelp/dirlib/remarks.html)明确要求查看服务坐标系，其本地资源大多为 CGCS2000。CGCS2000 不能在精密分析中无条件当作 WGS84。
- [高德](https://lbs.amap.com/api/javascript-api-v2/guide/transform/convertfrom)采用 GCJ-02；它不是把 WGS84 改一个投影编号。[百度](https://lbs.baidu.com/docs/jsapi?title=jsapi4%2Fguide%2Fconcept%2Fprojection)使用 BD09 经纬度及百度墨卡托 BD09MC，不能直接当作 EPSG:3857。均需专用适配，当前未支持。
- 科学分析应使用数据自身 CRS 和合适的分析投影，不应因切换底图而改变资产坐标基准。

在导航的「底图与定位」中选择地图源；标签可以拖至左、右或下方停靠区。地图顶部快捷选择框与组件保持同步。底图配置为当前服务器工作区共享配置，不属于会话分析图层；切换保留视角、分析图层和样式。

- 默认 OpenStreetMap，无需 Key。
- 天地图：展开设置，保存支持 WMTS 访问的服务 Key，再选择矢量或影像。注记随底图一并切换。请按自己的应用授权、服务配额及署名要求使用。
- 自定义源：导入一个 JSON 对象，或粘贴后导入。需明确来源使用的是 WGS84 对齐的 Web Mercator XYZ（EPSG:3857），而非 GCJ-02、BD09、TMS。浏览器直接请求公开 HTTPS 瓦片，提供者需允许跨域。地址不得包含私密凭据。不提供任意 URL 服务端代理。
- 经纬度定位接受 WGS84 经度、纬度，纬度范围为 ±85.05112878°；不包含地名搜索。

```json
{
  "name": "我的公开地图源",
  "url": "https://tiles.example.com/{z}/{x}/{y}.png",
  "attribution": "© 数据提供者",
  "projection": "EPSG:3857",
  "min_zoom": 0,
  "max_zoom": 19
}
```

以上是格式示例，不是真实瓦片服务。导入后还需选择该源。删除当前自定义源会恢复 OSM；内置源不可删除。

天地图 Key 保存在 Angelus state root 的 `geoint/basemaps.json` 中，原子写入、文件权限 0600，列表不回显。文件并非加密，请保护服务器账户及备份。清除 Key 时，如果当前为天地图会自动恢复 OSM。瓦片仅经固定官方 HTTPS 主机访问，不跟随重定向，限制读取大小和等待时间；服务失败时面板和状态栏提示，可手动恢复 OSM。不提供离线下载或批量预取。

本功能沿用本地工作台的信任边界；不要把未加认证的工作台暴露到公网。百度等需要专用坐标与瓦片网格适配的服务暂未支持，不能仅更换 URL。底图显示不是科学数据坐标精度验证。

模块：`geoint/basemaps.py` 管配置，`geoint/tianditu_tiles.py` 管固定主机读取，`api/geoint_basemaps.py` 管 HTTP；前端 `basemap-map.js` 管地图适配，`controllers/basemap-controller.js` 管工作流，`components/basemap-panel.js` 管视图。

验证：`.venv/bin/python -m unittest discover -s tests -p 'test_geoint_basemaps.py'`、`npm run test:geoint`、`npm run build:geoint`。天地图实际网络连通性仍需用自己的授权 Key 验证。

参考：[天地图 OpenLayers 接入文档](https://heilongjiang.tianditu.gov.cn/iportal/iClient/forJavaScript/docs/openlayers/ol.source.Tianditu.html)。
