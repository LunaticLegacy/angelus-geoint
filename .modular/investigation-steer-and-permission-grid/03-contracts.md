# 契约

`createAgent()` 增加 `steer(message)`：仅向当前选中会话的活跃运行发送：

```json
POST /api/runs/{session_id}/control
{"agent_id":"all","action":"steer","message":"..."}
```

`mountInvestigationChat({onSend, onSteer, onStop})`：当投影状态是 `running` 时，composer 标签为“调查引导”、按钮为“发送引导”，提交调用 `onSteer`；其它状态保持 `onSend`。输入框始终是同一 DOM 元素。

权限 DOM 的稳定语义不变：`.tool-items` 包含每个 `.tool-toggle`。列数由 CSS `repeat(auto-fit, minmax(...))` 决定，不写入状态、不影响勾选行为。
