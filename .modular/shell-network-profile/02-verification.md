# 验证

PASS

- `tests.test_session_shell_sandbox` 的四项测试通过，覆盖默认断网、共享网络和无效模式。
- `RunProfileStore` 冒烟验证确认默认模式为 `isolated`，并可持久化 `host_network`。
- `npm run test:geoint` 与 `npm run build:geoint` 通过；前端选择会立即持久化，并只影响下一次 Agent 构建。
- `host_network` 仅继承 Angelus 服务所在的网络命名空间，不能替服务所在命名空间创建公网出口。
