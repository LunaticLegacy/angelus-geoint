# 架构验证

PASS

状态与路径权威仍唯一：WorkspaceCatalog 决定宿主路径，session_sandbox 只接收已解析的单一路径。Shell 的可见文件系统由 mount 白名单定义，无法经 cwd 校验绕过。bwrap 缺失时拒绝而非回退，因此安全性质不依赖运行环境运气。

删除测试：移除 session_sandbox 仅使 Shell 工具不可用；不会破坏会话、Agent、资产或其他工具。替换 bwrap 实现只需保持 `create_session_shell_tool` 契约，Provider 无需变化。
