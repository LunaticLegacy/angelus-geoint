# 问题

现有 Shell 仅以 `cwd` 约束工作目录。命令仍在宿主权限下运行，能够使用绝对路径读取其他会话 `.angelus-state/sessions/*` 数据，造成会话边界穿透。

目标：将 Agent Shell 改为会话级 OS 沙盒。每次执行只挂载当前 Workspace 为 `/workspace` 可写目录；不挂载状态根、其他工作区与用户家目录；默认隔离网络、PID 与用户命名空间。

约束：保持工具名与 LLM 参数 `command/timeout/cwd` 兼容；不能把宿主路径透露给 Agent；bwrap 不可用或隔离能力不可用时必须拒绝执行，绝不能静默降级到宿主 Shell。

非目标：本轮不隔离 LLMFetcher、插件进程或外部 Agent Hub；只替换 RuntimeToolProvider 所提供的 Shell。
