# 分阶段实施计划（本轮停在设计）

| ID / 模块 | 输入 → 输出 | 允许文件范围 | 依赖 | 验收/测试 |
|---|---|---|---|---|
| I0 装配与发布基础 | 当前core及store → 共享GEOINT实例/受管locator/锁/原子发布契约 | geoint/runtime.py, catalog/service.py, presentation.py, geoint_tool_provider.py, api/geoint.py, api/__init__.py, core.py的GEOINT装配, application_module/session_service.py内部生命周期guard | 无 | 非默认state_root下HTTP/Agent读同资产；并发新增不丢数据；全部authority策略；删除与发布竞态；原HTTP契约回归 |
| I1 类型/存储 | DTO+限额 → 流式暂存/hash/manifest | geoint/imports/{models,storage}.py；相关测试 | I0 | 路径注入/配额并发/中断/重传/跨session/TTL可恢复 |
| I2 安全预检 | 受管原件 → 候选/CRS/能力/问题 | geoint/imports/{inspector,worker}.py；夹具测试 | I1 | 五种格式正反例、ZIP穿越/炸弹/sidecar、依赖缺失、未知CRS、禁网、超时终止 |
| I3 派生准备 | 显式配置 → 可读GeoJSON/COG | geoint/imports/preparer.py；测试 | I2 | GPKG多层、CSV坏行、投影转换、分类nearest、NoData/多波段、显示容量上限 |
| I4 流程/API | service契约 → 任务及幂等发布 | imports/service.py, api/geoint_imports.py, runtime.py | I0–I3 | 恢复、幂等、取消、发布中断、权限检查；原件与显示表示端点正确 |
| I5 组件/控制器 | API → 拖放和导入向导 | frontend/geoint-src/{import-client,controllers/import-controller,components/file-drop-target,components/data-import/*,main}.js、必要组件CSS | I4 | Files与dock拖动不冲突；宽/窄停靠；缺session提示；浏览器进度；切session旧响应隔离；失败可重试；只通过MapDocument加层 |
| I6 集成与分发 | 全功能 → 可发布版本 | 对应测试、依赖声明、Vite产物、相关INDEX精确同步、docs | I0–I5 | 五种真实样例浏览器上图、字段/CRS/顺序、206 Range、重启会话恢复；pytest/JS/Vite；桌面GIS依赖打包和资源限制检查 |

所有阶段禁止重写 Angelus 会话/运行/连接器/上下文/ToolRegistry HTTP契约、修改原始数据、把危险表达式传给工具。内部GEOINT装配和session guard只作列明的最小集成，不重写Agent执行系统。

执行顺序：I0 → I1 → I2 → I3 → I4 → I5 → I6。每步失败回本步修复；若需要新依赖边界则先更新设计门禁。可以分批交付，但未通过对应格式验收不得在Capabilities标支持。
