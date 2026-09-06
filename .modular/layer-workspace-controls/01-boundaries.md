# 边界

`layer-panel` 拥有左侧图层 DOM、资产选择和文档编辑意图；不直接 fetch。

`main` 拥有当前会话请求、地图文档读取与 PUT 写入；不持有组件 DOM 状态。

`import-controller` 拥有上传与受控导入事务；不关心 dock 位置。

`MapPresentationStore` 继续唯一拥有 groups、layers、title 与有效文档合并；不关心 UI 布局。

`dock-layout` 只拥有面板位置与标签；默认图层位于 left。
