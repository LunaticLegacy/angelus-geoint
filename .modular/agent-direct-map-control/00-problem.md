# 问题

GEOINT Agent 当前只能写入 `agent_proposal`，而不是当前用户实际看到的地图文档；在 user_override 策略下，提议甚至可能不进入有效图层。这不符合已被授予“管理地图图层”权限的 Agent 直接操作当前会话地图的预期。

目标：移除 Agent 的通用地图呈现提议工具；将受限的 `geoint_manage_map_layers` 改为对当前会话有效地图执行直接、可验证的 add/remove/reorder 写入。

非目标：不允许 Agent 接收路径、URL 或任意文档字段；不删除原始资产；不绕过当前会话资产绑定检查。
