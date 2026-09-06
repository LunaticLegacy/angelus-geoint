# 边界

`execution_service`：拥有控制命令接受与 `agent:control` 审计事件；不知道 DOM。

`llmfetcher Agent`：拥有安全边界的 steer 消费与 `agent:steer_applied` 事件；不知道会话 UI。

`investigation-event-projector`：拥有日志到调查时间线节点的投影；不请求 API、不改变执行状态。

`investigation-chat`：拥有 composer 标签、可用性和时间线 DOM；不知道 HTTP 或 Agent 内部队列。

`agent-controller`：拥有 HTTP 控制调用；不解释 Agent 事件。
