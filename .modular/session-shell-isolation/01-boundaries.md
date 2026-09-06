# 边界

`session_sandbox` 拥有 bwrap 命令构造、最小宿主运行时挂载、Shell 进程生命周期与安全失败语义；不读取会话上下文或配置。

`RuntimeToolProvider` 只解析当前 Session 的 Workspace，并把受控路径交给 `session_sandbox`；不拼装 bwrap 参数。

`WorkspaceCatalog` 是 Session → workspace 路径的唯一权威；Agent 提供的 `cwd` 只能是沙盒内 `/workspace` 的相对位置。

`llmfetcher` 不再提供该 Shell；它仍提供其他工具与执行控制。
