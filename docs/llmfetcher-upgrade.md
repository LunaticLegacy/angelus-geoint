# llmfetcher ContextItem 升级迁移 — 变更说明

本次升级把 `llmfetcher` 线性上下文从旧的 `LLMContext` 数据模型切换到新的
`ContextItem` 判别联合（`UserContextItem` / `AssistantContextItem`），并把
checkpoint 的持久化格式从「单文件内联 JSON」改为「SQLite 指针 + sidecar 数据库」。
本文记录 angelus 侧的适配范围、旧数据兼容策略、迁移命令与验收方式。

旧数据的默认行为是**绝不静默丢历史**：读方向同时认旧格式，写方向只写新格式，旧
格式到新格式的转换是一个显式、带备份、失败即中止的迁移动作。

## 1. 变更概览

| 关注点 | 旧（`LLMContext`） | 新（`ContextItem`） |
|---|---|---|
| 消息类型 | 单一 `LLMContext` 记录，`role` 字段区分 | `UserContextItem` / `AssistantContextItem` 判别联合 |
| 主键 | 无稳定 id | `ContextItemId`（`ContextItemId.new()` 工厂 / 确定性 id） |
| reasoning 字段 | `content_reasoning` / `reasoning_content` | `AssistantContextItem.reasoning` |
| usage 字段 | 短名 mapping（`input`/`output`/`total`...） | `TokenUsage`（`input_tokens`/`output_tokens`/...） |
| 工具调用 | `ToolInfo`（`call.name`/`call.arguments`/`result`） | `ToolCallRecord` + 独立 `ToolResultRecord`（指向 `result_id`） |
| checkpoint 文件 | 单文件 `{"compress_threshold", "messages": [...]}` | 指针 `{"storage": "sqlite", "database": "...", "round", "message_count"}` |
| 行存储 | 内联在 JSON 里 | sidecar `context.json.sqlite3`，分页读取 |

判定一个文件是哪种格式用 `is_sqlite_context_pointer(payload)`（来自
`llmfetcher.context_handlers.linear.paging`）。

## 2. 受影响的 angelus 代码

### 2.1 `angelus/modules/external_agent_hub_module/context_exchange.py`（P0 修复）

外部上下文导入/导出服务。`append_package` 把外部 package 的历史记录写回某个
Session Agent 的上下文，此前构造的是已下线的 `LLMContext`，升级后改用
`UserContextItem` / `AssistantContextItem` + `ContextItemId.new()`，因此
`handler.save()` 不再抛异常。

角色白名单语义保持不变，并显式统计「拒绝」：

- 只有 `user` / `assistant` 记录能映射成可持久化的上下文项；
- `system` / `tool` / 未知 role 属于历史文本、没有对应的持久化语义，计入
  `rejected_messages`，**绝不静默丢弃**（`ContextTransferResult.rejected_messages`
  会如实上报）；
- 导入的工具调用只保留为 package 内的文本，不会被实体化成可执行的 `ToolInfo`。

### 2.2 `angelus/modules/application_module/legacy_context.py`（读方向兼容 + 迁移内核）

新增只读兼容层，保证旧 checkpoint 在任何时候都能读全：

- `checkpoint_format(path)` → `v2-sqlite` / `legacy-json` / `missing` / `unreadable`；
- `read_checkpoint(path)`：读方向单一入口，`legacy-json` 走 `decode_legacy_checkpoint`，
  `v2-sqlite` 走分页 `read_persisted_context_page`，两种格式都能返回完整历史；
- `decode_legacy_checkpoint(path)`：把旧内联文档解成当前 `ContextItem` 并集。没有
  直接 v2 对应类型的行（`system` / `tool` / 未知 role）会被保留为带
  `PRESERVED_ROW_PREFIX` 标记的 user 文本，并通过 `preserved_rows`（按 timeline）
  显式上报——损失可见而非静默；
- `promote_checkpoint(path, *, apply=False)`：旧格式 → v2 的显式转换。`apply=False`
  只报告（`planned`），`apply=True` 才写指针并在旁边留一份
  `context.json.legacy.bak` 原样备份；写入失败则抛 `LegacyContextError` 且原文件不动。

### 2.3 `scripts/migrate_context_to_v2.py`（运维入口）

扫描一个 state root，对每个 `context.json` 分三类报告：

- **current**：已经是 v2 SQLite 指针，不动；
- **planned / promoted**：有行的旧 JSON，干跑时报告 `planned`，`--apply` 时 `promoted`；
- **empty / unreadable / failed**：空旧文档、无法识别、解码或写入失败——一律原样
  保留并计入 failures。

默认干跑，不加 `--apply` 不写任何东西。退出码：`0` 全部可用，`1` 有 checkpoint 需要
人工处理（failures 非空），`2` state root 存在但不是目录。

## 3. 迁移步骤（运维）

1. 停止后端，确保没有进程在写 checkpoint。
2. 先干跑，核对三分报告：

   ```bat
   set PYTHONPATH=.
   .venv\Scripts\python.exe -X utf8 scripts\migrate_context_to_v2.py <state-root>
   ```

3. 确认 `would promote` 的数量符合预期、`failures` 为空或已人工确认后，再落地：

   ```bat
   .venv\Scripts\python.exe -X utf8 scripts\migrate_context_to_v2.py --apply <state-root>
   ```

4. 每个被提升的 checkpoint 旁边都会保留 `<state-root>/.../context.json.legacy.bak`，
   即原始文档原样副本；如需回滚，把它拷回 `context.json` 即可。

`<state-root>` 既可以是整个 angelus state 目录，也可以是单个 `context.json`。
脚本对已是 v2 的 checkpoint 幂等，可重复执行。

## 4. 不静默丢历史的保证点

| 场景 | 行为 | 位置 |
|---|---|---|
| 旧内联 checkpoint 被新版 `ContextHandlerLinear.load` 读取 | 返回 `False`（不迁移），但 `read_checkpoint` 仍能读全 | `legacy_context.py:read_checkpoint` |
| `system` / `tool` / 未知 role 的旧行 | 保留为带 `[legacy <role> row preserved]` 标记的文本，计入 `preserved_rows` | `legacy_context.py:_decode_row` |
| 外部 package 里无法映射的 role | 计入 `rejected_messages`，如实上报 | `context_exchange.py:append_package` |
| 旧行不是 object / 文档非法 | 抛 `LegacyContextError`，迁移脚本记为 failure 并原样保留 | `legacy_context.py:decode_legacy_checkpoint`、`migrate()` |
| 迁移写入失败 | 抛错、原文件保持不动、备份已存在 | `legacy_context.py:promote_checkpoint` |

## 5. 测试覆盖

- `tests/test_external_agent_hub.py`：import → save → load → 分页读取 round-trip；
  rejected-role（`system` / `tool` / 未知 role）计入 rejected 且持久化历史不丢；
  重复 import 追加而非覆盖。
- `tests/test_paged_context_storage.py`：
  - `LegacyContextCompatibilityTests`：旧文档经 `read_checkpoint` 全量读回（含 reasoning
    与 preserved 行）、`promote_checkpoint` 备份 + 写 v2 指针 + 幂等、不可读文档原样
    保留、空旧文档报 `empty`、不可映射角色计入 `preserved_rows`；
  - `MigrationScriptTests`：`migrate()` 干跑只报告不写、apply 才提升且备份、
    单个坏 checkpoint 记为 failure 但不中断扫描、缺失 root 不算失败。

## 6. 已知后续项

- `scripts/INDEX.md` 需要补一行登记 `migrate_context_to_v2.py`（本次改动范围不含该
  索引文件，作为后续跟进）。
- 压缩（compaction）相关代码在新模型下的行为沿用 `ContextHandlerLinear` 既有实现，
  本升级不改压缩策略，只适配数据模型与持久化格式。
