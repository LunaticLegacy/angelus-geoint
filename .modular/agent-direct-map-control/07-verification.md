# 验证记录

PASS

- `GeoIntToolProvider` 不再向 Agent 暴露 `geoint_propose_map_presentation`。
- `geoint_manage_map_layers` 只允许添加已绑定资产、移除当前图层或完整重排当前图层，并经 `MapPresentationStore.put` 直接写入当前会话的用户地图文档。
- `tests.test_geoint_runtime.GeoIntRuntimeTests.test_authorized_agent_directly_updates_current_session_map` 通过，确认 Agent 写入 `user_overrides`，不会产生 Agent proposal。
- 原有的三项地图呈现单元测试通过；HTTP/TestClient 旧测试在当前 Python 3.14 环境的应用 lifespan 阶段阻塞，和本次改动无关。
- 前端在收到成功的 `geoint_manage_map_layers` 完成事件后刷新当前会话地图；`npm run test:geoint` 和 `npm run build:geoint` 均通过。
- GEOINT 工具权限视图仅隐藏 `swarm` 类别；后端注册、已有运行档案和会话 Swarm 不变。
