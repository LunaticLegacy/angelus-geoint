# 契约

执行服务在成功入队后写入：`agent:control`，其中 `data.action == "steer"`、`message` 为引导文本、`data.target_agents` 为接收者。

Agent 在安全边界消费后写入：`agent:steer_applied`，其中 `agent` 为已消费的 Agent、`data.round` 为生效轮次、`data.messages` 为已消费文本。

投影节点：`steer_queued` 与 `steer_applied`。前者显示“已排队”，后者显示具体 Agent 和轮次；两者不声明全体 Agent 都已应用。

Composer 模式：`running -> steer`；`completed|failed|stopped|interrupted -> follow_up`；其余可用会话 -> question；`stopping|force_stopping` 禁用。
