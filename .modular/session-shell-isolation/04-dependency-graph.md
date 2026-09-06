# 依赖图

`runtime_provider -> session_sandbox`

`runtime_provider -> workspace_catalog`

`session_sandbox -> subprocess`

`session_sandbox -> llmfetcher.Tool contract`

禁止：`session_sandbox -> AngelusCore`、`session_sandbox -> state_root`、`session_sandbox -> session context`、`runtime_provider -> llmfetcher.create_shell_tools`。
