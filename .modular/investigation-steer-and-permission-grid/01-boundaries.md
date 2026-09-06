# 边界

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `agent-controller` | 调用运行 API、维护流订阅和投影运行状态 | 组件 DOM 与排版 |
| `investigation-chat` | 根据投影状态渲染同一个 composer，并将用户意图交给回调 | HTTP、执行状态持久化 |
| `tool-permissions` | 从权限目录渲染勾选意图 | 决定列数、保存运行档案 |
| `geoint.css` | 响应式网格及可访问视觉状态 | 权限语义 |

删除 `agent-controller` 会使开始/steer 失效；删除聊天组件只失去 UI；删除权限组件只失去权限编辑 UI。运行状态仍唯一由 projector/API 事实拥有。
