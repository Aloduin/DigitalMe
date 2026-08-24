# DigitalMe Memory Engine v0.1 开发需求拆解

本计划采用“可运行纵向切片 + 阶段 Gate”。任务编号可直接用于 issue/backlog。

## 总体验收路径

```text
本地初始化
  → 导入一个真实来源
  → 浏览原始 Session/Message
  → 验证幂等与脱敏
  → 提取 Episode
  → 生成带 Evidence 的 Memory Candidate
  → 用户确认/修订 Durable Memory
  → 检索并回溯原始证据
```

## Phase 0 — 工程基线

目标：建立可持续开发、测试和迁移的最小工程。

### FND-001 Python 项目与依赖管理（P0）

- 使用现有 Python 3.13。
- 所有依赖通过 `uv add` 管理并提交 `uv.lock`。
- 配置运行依赖：FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、Typer。
- 配置开发依赖：pytest、pytest-asyncio、httpx、ruff、mypy。
- 增加 `uv run` 对应的 lint、typecheck、test 命令说明。

验收：全新 checkout 执行 `uv sync` 后，测试和 CLI help 可运行。

### FND-002 包结构与配置（P0）

- 建立 `backend/digitalme` 包及 config、db、ingestion、privacy、memory、retrieval、api、cli 边界。
- 配置只从环境变量/配置文件读取，路径统一 expand/resolve。
- DeepSeek Provider 从根目录 `.env` 读取 `API_KEY` 和 `API_BASE_URL`；禁止在 import time 或日志中输出配置值。
- 生成 `.env.example`，只包含空值和说明，不得包含真实凭据。

验收：未配置 LLM 时服务仍可启动，配置错误给出可操作错误信息。

### FND-005 Git 与远程同步工作流（P0）

- `.env`、数据库、Raw Store、缓存、真实导入数据必须被 `.gitignore` 排除。
- 每个纵向切片使用小步、语义清晰的提交；提交前检查 `git diff` 和 `git status`。
- 提交前运行该切片相关的 lint、typecheck 和 tests。
- push 前先获取远端引用并确认本地分支没有落后或分叉；存在冲突时停止并人工处理。
- 禁止强推、破坏性 reset 或覆盖他人未合并修改，除非用户明确授权。
- 建议在 CI 增加 secret scan 和 `uv sync --locked` 验证。

验收：`.env` 不出现在 Git 状态中；仓库可从干净 checkout 用锁文件复现；远端同步无未解释的分叉。

### FND-003 数据库与迁移（P0）

- SQLite engine 开启 foreign keys、WAL 和 busy timeout。
- Alembic 初始迁移包含 Core 所需表和约束。
- 测试使用临时数据库，不能触碰用户数据。

验收：upgrade、downgrade、再次 upgrade 均通过；应用不隐式建表。

### FND-004 可观测性与错误模型（P1）

- 结构化日志，默认不记录 message body、prompt 和 secret。
- 统一 domain error / API error / CLI exit code。
- 每个 ingestion job 带 correlation ID。

验收：一次失败导入能定位 source、artifact、stage 和安全的错误摘要。

**Phase 0 Gate**：CI/本地质量命令通过；空数据库可迁移；CLI/API 启动成功；secret 和本地数据未被 Git 跟踪。

## Phase 1 — Historical Archive（v0.1 Core）

目标：可靠回答“过去发生过什么”，不依赖 LLM。

### ARC-001 Source 与 Artifact Store（P0）

- 实现 source registration。
- 流式计算 SHA-256，按内容寻址保存 artifact。
- 原子写入：临时文件完成后 rename。
- 重复 artifact 返回已有记录。
- 定义软删除与物理清除 service。

验收：相同字节导入十次只产生一个 artifact；中途失败不留下半文件。

### ARC-002 Canonical Session Schema（P0）

- 定义 versioned Session、Message/Event Pydantic schema 和 ORM model。
- 保留外部 ID、parent relation、raw locator、raw timestamp 和 warnings。
- 支持 text、multimodal placeholder、tool/event metadata，未知类型不导致整批失败。

验收：schema round-trip；未知字段被保留或产生明确 warning。

### ARC-003 Ingestion Job 状态机（P0）

状态建议：`pending → running → completed | completed_with_warnings | failed | cancelled`。

- 记录阶段 checkpoint、计数、错误和重试。
- 进程重启后可识别并恢复/重置悬挂 job。
- 阶段写入使用事务与唯一约束。

验收：在 artifact、parse、persist 阶段注入故障后重跑，结果无重复。

### ARC-004 ChatGPT Export Discovery（P0）

- 安全读取 ZIP，阻止 zip-slip 和解压炸弹。
- 查找单个或多个 conversation JSON。
- 输出 manifest 与无法识别文件报告。

验收：覆盖标准导出、多 JSON、损坏 ZIP、恶意路径和超限压缩比 fixture。

### ARC-005 ChatGPT Conversation Adapter（P0）

- 解析 conversation mapping/tree。
- 保留所有节点与父子关系。
- 标识 current/selected branch；下游不静默合并互斥分支。
- 处理空节点、缺失时间、未知 content type 和删除消息。

验收：多分支 fixture 的节点数、边关系、顺序和文本与 golden data 一致。

### ARC-006 Codex Rollout Discovery（P0）

- 配置式扫描 active/archived session roots。
- 流式读取 JSONL，支持超大文件。
- 用 inode/path/size/mtime 仅作发现提示，最终身份依赖内容与外部 ID。

验收：重复扫描无重复；单行损坏产生 warning 且不吞掉其余有效事件。

### ARC-007 Codex Adapter（P0）

- 解析已知 `session_meta`、message、response item、tool interaction 等事件。
- 未知事件保存在 Raw 并记录类型，不阻塞导入。
- 实现 keep/selective/summary/drop policy 的确定性预处理；Core 阶段不调用 LLM summary。

验收：fixture 中用户消息、最终回复、工具摘要和事件顺序正确，未知事件可追踪。

### ARC-008 Secret Scanner 与 Redacted View（P0）

- 路径/类型 denylist。
- 常见 secret pattern 与高熵候选检测。
- 生成 redaction spans 和稳定的 redacted text。
- provider policy gate 在任何模型调用前强制执行。

验收：测试语料中的 API key、token、password、private key、Authorization 均不进入 redacted view、日志或异常。

### ARC-009 Session CLI/API（P0）

- CLI：ingest、jobs inspect、sessions list/show。
- API：创建导入 job、查询 job、sessions list/detail。
- 支持分页、source/time filter；message body 详情按需加载。

验收：从 CLI 导入 fixture 后，可通过 CLI 与 API 追溯到 artifact locator。

### ARC-010 Core 集成与规模测试（P1）

- 建立脱敏后的 ChatGPT/Codex fixtures。
- 连续导入、失败恢复、删除级联、10k session 列表测试。
- 输出 import completeness、parse warning、duplicate rate 报告。

**Phase 1 Gate**：两个来源均可导入和浏览；重复导入零新增；secret 外发面为零；任一 message 可回溯 Raw locator。

## Phase 2 — Episodic Memory

目标：把长 Session 转化为少量可解释 Episode。

### EPI-001 Session Segmentation（P0）

- 先实现确定性分段：时间间隔、turn 数、显式 topic boundary、Codex task boundary。
- 分段结果版本化，可重建。

验收：相同输入和版本产生相同 segments；边界均能回到 message IDs。

### EPI-002 Episode Extraction Contract（P0）

- Pydantic schema：type、title、summary、time range、projects、decisions、open questions、source spans。
- prompt 明确禁止无证据细节，输出严格 JSON。
- 校验每个 source span 都属于输入 segment。

验收：无效 JSON、越界证据和缺失字段不会写入 episode。

### EPI-003 Model Run Audit（P0）

- 保存 provider/model/config hash、prompt version、input hash、输出、验证错误和耗时。
- 输入只引用 redacted view；敏感 provider gate 生效。
- 支持 mock provider 和离线测试。

验收：任意 episode 可定位生成它的 model run 和输入 hash。

### EPI-004 Episode Review CLI/API（P1）

- list/detail/rebuild。
- 展示 source sessions/messages、pipeline version 和 extraction warning。

**Phase 2 Gate**：golden sessions 能生成预期 episode；每个 episode 至少有一个有效 source span；换 prompt 版本可并行重建而不覆盖旧结果。

## Phase 3 — Durable Memory

目标：形成受证据和用户治理约束的长期记忆。

### MEM-001 Memory Candidate Schema（P0）

- 实现文档中 memory type、scope、confidence、salience、temporal、sensitivity、evidence strength。
- E0 丢弃；E1 强制为 hypothesis/uncertain。
- 每个 candidate 至少关联一个 evidence。

验收：违反 evidence/type/scope 规则的 candidate 无法持久化。

### MEM-002 Evidence Model（P0）

- 保存多级引用、raw hash、locator、normalized offsets、redacted quote snapshot。
- 读取时校验 hash 并标记 stale。

验收：Memory → Episode → Message → Artifact 双向可查。

### MEM-003 Resolver（P0）

- 先使用确定性预筛选：type、subject、predicate、scope、entity 和 time overlap。
- 输出 reinforce/refine/supersede/dispute/create 建议。
- LLM 只能提出 relation proposal，写入前通过规则验证。

验收：覆盖重复、作用域不同、时间演化和真实冲突四类 golden cases。

### MEM-004 Revision 与 User Override（P0）

- 所有 edit/status/scope/sensitivity 变化创建 revision。
- 实现 USER_CONFIRMED、USER_EDITED 和否定 tombstone。
- consolidation 不得覆盖用户确认内容。

验收：用户否定后重跑 extraction/consolidation，不会自动复活同义记忆。

### MEM-005 Consolidator（P1）

- 定期处理重复、晋升、关系、衰减和 Self Model 候选。
- dry-run 输出变更集；默认先 review 后 apply。
- Raw 与用户治理状态不受 rebuild 影响。

验收：dry-run 可解释每项建议；重复执行不产生额外变化。

### MEM-006 Memory CLI/API（P0）

- list/detail/evidence/confirm/edit/dispute/delete/pin/change scope/sensitivity。
- 任何危险删除显示影响范围；物理清除需要显式参数。

**Phase 3 Gate**：Memory 必有 Evidence；A→B 演化不覆盖 A；用户修订在全量重建后仍保留。

## Phase 4 — Retrieval and Ask

目标：基于少量高价值上下文回答个人问题，并完整引用证据。

### RET-001 FTS5 Index（P0）

- 索引 memories、episodes 和 selected messages。
- 支持 rebuild、增量更新和删除同步。
- 中文 tokenization 能力需实测；不足时引入可替换 tokenizer，不假设默认 FTS5 足够。

验收：golden queries 的 Recall@K 达到预设基线，删除内容不再命中。

### RET-002 Filter and Ranking（P0）

- scope、project/entity、time、status、sensitivity filter。
- ranking 分离 query relevance 与 salience/confidence/recency/pinning。
- 返回分数组成，便于调试。

验收：project scope 和 temporal cases 不发生明显串线。

### RET-003 Memory Pack Builder（P0）

- 预算化选择 self context、memories、episodes、contradictions、open loops。
- 去重，保留支持和反例，附 evidence refs。
- provider policy 再次过滤 sensitivity。

验收：固定 token/字符预算不溢出；每个结论块带可解析引用。

### RET-004 Ask Service（P0）

- 回答中区分 explicit fact、behavioral evidence 和 inference。
- 无足够证据时明确拒绝形成确定结论。
- API/CLI 返回答案、citations、retrieval diagnostics（可选）。

验收：完成设计文档 Case 10，并能点回原始 Session/Message。

### RET-005 Optional Vector Retrieval（P2）

- 在 FTS baseline 后评估 sqlite-vec 和 embedding provider。
- 仅在 golden dataset 指标有明确提升时启用默认 hybrid ranking。

**Phase 4 Gate**：三个核心 Demo 至少完成第一个；回答包含时间线、明确/推断区分、反例和证据引用。

## Phase 5 — Memory Management UI

目标：提供用户治理和证据回溯界面。

### UI-001 App Shell 与 Dashboard（P1）

- source/job 状态、sessions/episodes/memories/open loops 统计。
- 默认不展示敏感正文。

### UI-002 Session Viewer 与 Timeline（P1）

- 支持 conversation tree、episode timeline、Raw locator 和 warning。

### UI-003 Memory Explorer/Inspector（P0）

- filter/search/detail/evidence/revisions/relations。
- confirm/edit/dispute/delete/pin/scope/sensitivity 操作。

### UI-004 Evidence Navigation（P0）

- Memory → Episode → Session → Message。
- hash mismatch/stale evidence 明确告警。

### UI-005 前端安全与可访问性（P1）

- 内容作为不可信文本渲染，禁止未净化 HTML。
- destructive action 二次确认，键盘导航和基础响应式布局。

**Phase 5 Gate**：用户可完整检查、纠正和删除一条 Memory，并追溯其所有 Evidence 和 revision。

## 横切需求

### TST-001 Golden Dataset（P0，从 Phase 1 开始持续）

- 脱敏、小而覆盖关键边界。
- 保存 expected sessions、episodes、memories、relations、evidence。
- 格式变更必须附 regression fixture。

### SEC-001 Threat Model（P0）

- 覆盖恶意 ZIP/JSON、prompt injection、secret exfiltration、路径穿越、超大输入、HTML injection。
- Source content 中的指令永远是数据，不是系统指令。

### OPS-001 Backup/Restore/Delete（P1）

- 一致性备份数据库和 Raw Store manifest。
- restore 校验 artifact hash。
- source 删除报告受影响的派生对象。

### DOC-001 Operator Documentation（P1）

- `uv` 安装、初始化、导入、故障恢复、数据目录、隐私策略。
- 文档命令必须在干净环境中验证。

## 建议的首轮实现顺序

第一轮只领取下列 P0 任务：

1. FND-001 ～ FND-003
2. ARC-001 ～ ARC-003
3. ARC-004、ARC-005、ARC-008、ARC-009（先完成 ChatGPT 纵向切片）
4. ARC-006、ARC-007（复用同一流水线接入 Codex）
5. ARC-010，冻结 v0.1 Core

在 Phase 1 Gate 通过之前，不启动 Web UI、向量检索或自动 consolidation。

## Definition of Ready

任务进入开发前必须具备：

- 明确输入、输出和错误行为。
- 至少一个正常 fixture 和一个失败/边界 fixture。
- 数据迁移与删除影响已说明。
- 涉及模型时已有 schema、prompt version 和离线 mock。
- 验收标准可由自动化测试或明确的人工步骤验证。

## Definition of Done

- 实现与迁移已提交。
- 单元/集成测试覆盖正常、失败、幂等和安全路径。
- `uv run` 下 lint、typecheck、test 通过。
- 没有真实个人数据、secret、数据库或缓存进入仓库。
- CLI/API 错误可操作，日志不泄露正文和凭据。
- 用户可从派生对象回溯到来源；必要时可删除并重建。
