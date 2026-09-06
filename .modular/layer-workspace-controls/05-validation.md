# 架构验证

PASS

地图文档仍是 groups/layers/title 的唯一真源；UI 仅产生 `move` 意图，main 将其适配为既有 API 的一份完整、受校验的文档写入。资产选择不暴露本机路径且按 session 过滤。没有新增后端模块、循环依赖或绕过 MapPresentationStore 的写入。
