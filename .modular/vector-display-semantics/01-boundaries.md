# 边界

`mapping.vector_style` 只定义安全的默认矢量样式记录；不读取资产、路径或浏览器状态。

`MapPresentationStore` 校验并持久化 `Layer.render`；它不依赖 OpenLayers。

`layer-panel` 编辑颜色和透明度并发送普通 `patch` 意图；它不发起网络请求、也不生成地图样式对象。

`map-layer-sync` 将已校验的样式记录转换为 OpenLayers `Style`；它不写入会话地图文档。

`main` 沿用已有 map-document PUT 链路，不引入另一份图层样式存储。

`GeoIntToolProvider` 将 Agent 的有限颜色参数转换为 `set_vector_style`
操作；它不接受任意 render JSON，最终仍只写入 `MapPresentationStore`。
