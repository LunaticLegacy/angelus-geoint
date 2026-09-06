# 实施计划

1. 创建 session_sandbox 模块，构造最小 bwrap mount namespace 并实现 Tool handler。
2. 用 RuntimeToolProvider 替换 LLMFetcher cwd-only Shell 工厂。
3. 添加构造参数与拒绝 host cwd 的单元测试；在支持 bwrap 的环境中执行跨会话读取拒绝回归测试。
4. 执行相关 Python 测试、前端无关回归与静态检查。
