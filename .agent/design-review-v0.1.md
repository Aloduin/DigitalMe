# DigitalMe Memory Engine v0.1 设计审查

审查对象：`docs/DigitalMe Memory Engine v0.1 项目设计文档.md`

审查结论：**方向正确，但需要在编码前补齐若干工程契约；建议缩小首个可交付版本并采用纵向切片。**

## 1. 已成立的核心设计

以下判断应作为架构约束保留：

1. `Raw Experience → Episode → Durable Memory → Self Model` 的分层合理，避免把聊天切片和长期记忆混为一谈。
2. Memory 必须显式关联 Evidence；无法追溯的模型结论只能是候选或假设。
3. Confidence、Salience、Scope、Temporal validity 和 Status 是相互独立的维度，不能合并为单一分数。
4. Raw Store 与 Retrieval Index 分离；Embedding 是可重建索引，不是事实来源。
5. 用户修订优先于模型推断，并保留 revision history。
6. Local-first、SQLite、CLI-first 与当前 MVP 阶段匹配。
7. Codex 接入只读，内部 schema 通过 Adapter 隔离。

## 2. 编码前必须补齐的设计

### 2.1 MVP 范围需要收缩

原设计同时包含两个 importer、持续监听、Episode、Memory resolver、consolidation、混合检索、Self Model、API 和五个前端页面，无法作为一个低风险 MVP 一次性交付。

建议定义两个交付边界：

- **v0.1 Core**：CLI + ChatGPT/Codex 历史导入 + Session 浏览 + 幂等与脱敏；不依赖 LLM 即可验收。
- **v0.1 Memory**：在 Core 稳定后增加 Episode、Memory/Evidence、冲突处理、FTS 检索和 Ask；Web UI 最后接入。

每个阶段必须形成可运行的纵向切片，而不是先创建全部空目录和接口。

### 2.2 “Raw 永久保留”需要隐私例外

“永不覆盖”可以作为审计原则，但“永久保留”与用户删除权、误导入密钥、磁盘生命周期冲突。

采用以下规则：

- Raw artifact 写入后不可原地修改。
- 用户可以删除整个 source、artifact 或 session；删除必须级联清除派生数据和索引。
- 默认使用可审计的软删除；对于 secret、合规删除或用户明确要求，支持物理清除。
- 任何模型只读取经过脱敏的派生视图，Raw 文件不直接进入 prompt。
- 备份、日志、临时文件也必须遵守删除和 secret policy。

### 2.3 Canonical Schema 需要版本化

ChatGPT conversation tree 和 Codex rollout 都会变化。Canonical Session、Message 和 Event 必须包含：

- `schema_version`
- `source_type`、`source_external_id`
- 稳定的内部 ID
- 原始 payload 的 artifact 引用和定位信息
- `parent_id`/分支信息
- 时间戳原值、解析值和时区处理状态
- content type、文本化结果及解析警告

ChatGPT 的分支会话不能静默压成单线。首版应保存完整树，并显式选择“当前分支”用于下游提取。

### 2.4 幂等性应按流水线阶段定义

仅有 `source + external_id + content_hash` 不足以保证模型派生结果可复现。建议使用：

- Artifact identity：`sha256(raw_bytes)`。
- Canonical identity：`source_type + external_id + canonical_schema_version`。
- Derived identity：`input_hash + pipeline_version + prompt_version + model/provider config hash`。
- 每个阶段使用唯一约束或 upsert，事务提交。
- 失败任务记录 checkpoint、错误类别和 retry count，可安全重跑。

### 2.5 模型调用需要一等公民的审计模型

除 `LLMProvider` 接口外，需要保存 `model_runs`：

- provider/model、参数与调用时间
- prompt/template version
- 输入引用及脱敏版本 hash
- 结构化输出、验证错误与重试次数
- token/费用/延迟（provider 可提供时）

所有结构化结果先通过 Pydantic schema 验证；失败不得污染 Durable Memory。

### 2.6 Evidence 定位不能只靠 quote offsets

字符 offset 会因规范化、Unicode 和脱敏而漂移。Evidence 至少保存：

- artifact/session/message/episode ID
- 原始内容 hash
- JSON pointer 或 JSONL line/event ID
- normalized text 的 start/end
- quote snapshot（经过脱敏）

展示证据时校验 hash；失配则标记 evidence stale，而不是展示错误文本。

### 2.7 用户修改与冲突规则需要确定性

建议优先级：

`USER_CONFIRMED > USER_EDITED > E5 > E4 > E3 > E2 > E1`

规则：

- 用户否定不会删除历史候选，而是产生 tombstone/revision，阻止相同推断自动复活。
- Scope 不同的表述默认不冲突。
- 时间区间不重叠的表述优先视为演化，而非冲突。
- 无法确定是演化还是冲突时标记 `disputed`，不得自动二选一。
- 自动 consolidation 不能修改用户确认内容，只能提出待审候选。

### 2.8 Secret Filter 需要双层防线

单靠正则无法可靠覆盖秘密信息。首版至少包含：

- 文件路径与事件类型 denylist（`.env`、private key 等）。
- 高置信度 pattern scanner（常见 token、Authorization、URL credentials）。
- 熵/长度启发式作为补充，并控制误报。
- provider policy gate：`secret` 永不外发，`sensitive` 默认只允许 local provider。
- 测试保证异常信息、日志和 model_runs 中也不出现明文 secret。

### 2.9 Retrieval 的首版应先 FTS、后向量

FTS5 + scope/time/status filter 足以验证证据链与产品价值。`sqlite-vec` 和 embedding provider 应保持可选：

1. 先实现精确过滤和 FTS5。
2. 建立 golden queries 和 Recall@K 基线。
3. 只有向量检索能带来可测提升时再加入。

这能避免本地二进制依赖和 embedding 迁移提前阻塞核心流程。

### 2.10 API 应以异步 Job 语义表达导入

大型 ZIP 和 Codex 历史扫描不适合作为同步 HTTP 请求。API 应返回 `job_id`，提供状态、进度、错误报告和取消能力。CLI 与 API 调用同一个 application service，不能各自实现导入逻辑。

## 3. 推荐的基础数据边界

### 不可变事实层

- `sources`
- `artifacts`
- `sessions`
- `messages` / `events`
- `ingestion_jobs` / `ingestion_errors`

### 可重建派生层

- `episodes`
- `memory_candidates`
- `embeddings`
- FTS indexes
- `model_runs`

### 用户可治理状态层

- `memories`
- `memory_evidence`
- `memory_relations`
- `memory_revisions`
- `user_assertions` / tombstones
- `projects` / aliases

不可变事实层是来源记录；派生层可以按 pipeline version 重建；用户治理层必须迁移和备份，重建时不得丢失。

## 4. 非功能需求基线

- **安全**：外部模型请求中 secret 泄漏测试为零；默认绑定 localhost。
- **幂等**：同一 fixture 连续导入两次，核心对象数量不增加。
- **可恢复**：任意阶段失败后可从最近 checkpoint 重跑，不产生孤儿对象。
- **可观测**：每个 job 可查看阶段、计数、耗时、警告和错误。
- **可迁移**：数据库只由 Alembic 管理；禁止应用启动时隐式重建生产表。
- **可测试**：parser、normalizer、redactor 不调用真实外部模型即可完成确定性测试。
- **可移植**：Linux/macOS 为首要目标；所有本地路径通过配置解析，不把 `~/.codex` 写死在业务代码中。
- **性能初始目标**：10,000 sessions 的元数据列表与过滤在普通本机上可交互使用；大字段按需加载。

## 5. 主要风险与控制方式

| 风险 | 影响 | 控制方式 |
|---|---|---|
| 上游导出格式变化 | 导入失败或静默丢数据 | fixture 多版本、宽容读取、明确 warning、schema adapter |
| LLM 产生虚假记忆 | 破坏可信度 | candidate gate、证据必填、E1 仅 hypothesis、用户确认 |
| Codex 日志泄密 | 严重隐私风险 | 先过滤后模型、denylist、泄漏回归测试 |
| 重复/冲突记忆增长 | 检索质量下降 | 稳定 identity、resolver 规则、golden dataset |
| 一次构建过多功能 | 长期没有可验收版本 | Core/Memory 分界、纵向切片、阶段 gate |
| SQLite 扩展兼容性 | 安装与发布受阻 | FTS5 先行、向量扩展可选、能力探测 |

## 6. 当前建议决策

以下默认值可以直接用于开发：

- Python：3.13（项目已配置），统一使用 `uv`。
- 后端：FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic。
- CLI：Typer；CLI 与 API 共用 application services。
- 数据库：SQLite，启用 foreign keys 和 WAL；FTS5 首发，向量检索延后。
- ID：应用生成的 UUIDv7/ULID 风格字符串；外部 ID 不直接作为主键。
- 时间：数据库统一存 UTC，保留 source timezone/raw timestamp；UI 再转换时区。
- Raw Store：content-addressed filesystem；数据库保存 hash、size、media type 和路径。
- LLM：provider 可选；没有 provider 时 Core 全功能可用，Memory 阶段明确提示未配置。
- 默认云端 LLM Provider：DeepSeek；从根目录 `.env` 注入 `API_KEY` 和 `API_BASE_URL`，任何持久化记录只保存 provider/model 等非秘密元数据。
- Web UI：不作为首个 Core gate，先用 CLI/API 验证数据与证据链。

## 7. 设计文档建议修订项

后续更新正式设计文档时，应加入：

1. 数据删除、保留和备份策略。
2. Canonical schema 与 pipeline versioning。
3. ingestion job 状态机和失败恢复。
4. model run / prompt 审计模型。
5. 用户否定 tombstone 与 deterministic precedence。
6. v0.1 Core 和 v0.1 Memory 的明确边界。
7. 非功能验收指标与测试 fixture 要求。
8. 末尾未闭合的 Markdown 代码块修复。
