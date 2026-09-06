# 依赖图

```text
investigation-chat -> agent-controller -> /api/runs control
tool-permissions -> geoint.css
```

禁止：`investigation-chat -> api`、`tool-permissions -> session persistence`、CSS 影响策略值。
