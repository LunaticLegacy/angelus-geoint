# 依赖方向

HTTP → import-service → storage / inspector / preparer / catalog / presentation / session-lifecycle。
inspector/preparer → import-contracts + 受限 GIS worker；storage → import-contracts。
import-service 负责 worker 生灭和任务恢复，worker 不反向调用 HTTP/core。

main → file-drop-target / import-controller / data-import-panel。
drop/panel 通过注入回调向 controller 发意图，不导入 controller。
controller → import-client；完成回调交给 main 的现有 map-document 刷新流程。
桌面壳的 desktop-import-bridge 接收 OS 路径后直接向同一 loopback import API 流式上传；JS 只同步 session ID，并接收无路径的进度/预检快照。浏览器继续由 FileList → controller → client 上传。
map-core、Dock、basemap 不依赖 import，删除导入组件不破坏地图/会话/Agent。

GEOINT runtime → service/catalog/presentation/import-service；API 和 GEOINT 工具从同一个 core-scoped runtime 解析。runtime 不注册第二份 AngelusCore 或 Session。

架构 YAML 是本功能的待实施设计锁，不把新增模块伪称为当前实现。
