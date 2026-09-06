# 依赖图

```text
api / core / tests
       |
 angelus.geoint (facade)
  |      |       |      |      |
runtime analysis assets mapping ingestion agent
   |       |      |       |       |
   +-------+------+-------+-------+
                   |
              processing
```

允许方向：`runtime -> {analysis, assets, mapping, ingestion, processing}`；`ingestion -> {assets, mapping}`；`agent -> {assets, mapping, processing}`；`analysis` 不依赖其他 GEOINT 域包。

禁止方向：`mapping -> ingestion`、`assets -> ingestion`、`analysis -> mapping`、任何领域包导入 `api` 或 `core`。仅 `agent` 在 `TYPE_CHECKING` 中引用 `AngelusCore`。
