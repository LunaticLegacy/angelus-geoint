# 验证

Architecture: PASS
Implementation: PASS

- `agent-controller.steer()` 使用现有 `/api/runs/{session_id}/control`，无新增后端状态。
- 聊天组件复用原 `#agent-prompt` textarea；运行时仅切换提示、标签和提交意图。
- `.tool-items` 用 `repeat(auto-fit, minmax(min(100%, 12rem), 1fr))`，列数随容器实时变化。
- `npm run test:geoint` 通过，新增 steering transport 校验。
- `npm run build:geoint` 通过；保留既有 bundle-size 与 Node module-type 警告。
- 源文件 `git diff --check` 通过。Vite 生成的既有 minified bundle 中包含一处尾随空白，故全仓生成物检查会报告该行；未改变运行语义。
