# 计划

1. `agent-controller`：实现受 request scope 保护的 `steer` API 调用；验收为运行中的会话可收到 control receipt。
2. `investigation-chat` 和 `main.js`：注入 `onSteer`，依据投影状态复用同一个 textarea/快捷键；验收为运行时按钮与文案切换，终态恢复发起调查。
3. `geoint.css`：用自动适配列数的网格布局子工具；验收为宽度变化时列数变化且窄屏不溢出。
4. 添加或扩展前端测试，构建 GEOINT bundle。
