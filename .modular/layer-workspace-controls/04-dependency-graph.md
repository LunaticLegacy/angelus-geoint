# 依赖图

`layer-panel -> layer document contract`

`main -> layer-panel`

`main -> catalog assets API`

`main -> map presentation API`

`import-controller -> import API`

`dock-layout -> panel registry`

禁止：`layer-panel -> fetch`、`layer-panel -> asset storage`、`dock-layout -> map document`。
