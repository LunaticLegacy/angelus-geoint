# 契约

前端请求 `GET /api/geoint/catalog/assets?session_id={id}`，仅使用已绑定资产的 `id/name/format/kind`。

layer-panel 发出：`add`（`asset_id/title/group_id`）、`group-add`（`title`）、`patch`（含可选 `title`）、`move`（`id/group_id/ids`，一次表达拖入/拖出组及顺序）、`reorder`、`remove`。

main 将 `add` 转为既有 Layer 文档记录并以 `PUT /map-presentation` 写入；`group-add` 只追加合法 group；`patch title` 只改变 layer.title，不触碰 asset.name；`move` 校验图层 ID 与目标组后原子更新 `group_id` 和 z-index。

导入按钮在预检成功后自动提交所有可渲染候选；状态文本仍写入全局状态栏，不保留 DATA IMPORT 卡片。
