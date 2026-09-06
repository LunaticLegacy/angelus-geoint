# 实施计划

1. 从 GEOINT Agent registry 中移除提议工具。
2. 将 manage_map_layers 的最终写入由 propose 改为 put，并更新返回语义。
3. 增加回归测试，证明 add 直接出现在 effective/user_overrides 而非 agent_proposal。
4. 运行 GEOINT runtime 回归测试。
