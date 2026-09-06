# 契约

`RunProfile.shell_network_mode` 只能为：

- `host_network`：默认，Shell 继承 Angelus 服务进程的网络命名空间；仅当该服务本身具有出口时可联网，仍只挂载当前会话工作空间为可写位置。
- `isolated`：操作者可选，Bubblewrap 使用 `--unshare-net`。

该设置只在下次 Agent 构建时生效，并参与 Agent 指纹；运行中的 Agent 不会热更新。
