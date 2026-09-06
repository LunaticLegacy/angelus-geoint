# 契约

`create_session_shell_tool(workspace: Path, *, sandbox_binary="bwrap", max_timeout=60)` 返回一个名为 `shell` 的 LLM Tool，参数维持：`command: str`、`timeout?: number`、`cwd?: str`。

内部路径契约：`cwd` 为 `/workspace` 或其子路径时允许；相对路径解释为 `/workspace` 下路径；宿主绝对路径一律拒绝。

运行契约：bwrap 以 `--unshare-user --unshare-pid --unshare-net` 启动；`/workspace` 唯一可写 host mount；`/tmp` 为 tmpfs；运行时只读挂载白名单；进程以 2 GiB 虚拟地址空间和 256 文件描述符上限启动。缺少 bwrap 或启动失败返回明确错误文本，绝不运行未隔离回退。

Provider 契约：Materialized Shell 描述为“会话隔离工作区”，不承诺访问绑定工作区以外的位置。
