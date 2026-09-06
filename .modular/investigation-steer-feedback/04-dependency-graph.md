# 依赖图

`execution_service -> execution journal`

`llmfetcher Agent -> execution hook -> execution journal`

`agent-controller -> runs API`

`investigation-event-projector -> journal event schema`

`investigation-chat -> investigation-event-projector`

禁止：`investigation-chat -> runs API`、`investigation-event-projector -> execution_service`、`execution_service -> frontend`。
