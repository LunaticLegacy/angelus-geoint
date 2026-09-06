# 实现验证

PASS

- `python -m unittest tests.test_session_shell_sandbox tests.test_session_console`：通过。
- 真实 bwrap 集成回归通过：当前 workspace 可读写；`/home/luna` 不存在；相邻 session workspace 不存在；相邻 secret 未出现在输出中。
- Sandbox 以 user、pid、net、ipc、uts 命名空间运行，并清空环境；仅 runtime 白名单只读挂载和 `/workspace` 单一可写 host mount 存在。
- `git diff --check -- . ':!frontend/static/geoint-dist/main.js'`：通过。生成的既有前端 bundle 为单行第三方产物，不能使用 diff --check 的尾随空白规则。
