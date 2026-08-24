# DigitalMe Memory Engine v0.1 项目设计文档

**项目代号：** DigitalMe  
**子系统：** Memory Engine  
**版本：** v0.1  
**定位：** Local-first Personal Memory Agent / Digital Self Foundation  
**状态：** MVP Design

---

# 1. 项目概述

## 1.1 项目定义

DigitalMe Memory Engine 是 DigitalMe 数字分身系统的第一阶段核心基础设施。

它不是简单的：

> 聊天记录搜索工具

也不是：

> 把历史聊天全部做 Embedding 的个人 RAG

而是一个能够：

**采集个人数字经历 → 理解 Session → 提炼 Episode → 形成长期 Memory → 处理冲突与演化 → 在未来对话中按需恢复个人上下文**

的个人记忆系统。

v0.1 首先接入两个高价值数据源：

1. **ChatGPT Web 历史会话及已有 Memory**
2. **Codex Desktop / CLI Session 与 Codex Memory**

通过历史数据初始化 DigitalMe 的“过去”，随后持续接收新的 Session，并逐渐构建长期可维护的个人记忆。

---

# 2. 核心目标

DigitalMe Memory Engine v0.1 要回答的核心问题不是：

> “过去哪段聊天里出现过 SQLite？”

而是：

> “我为什么经常在个人项目 MVP 阶段选择 SQLite？”

进一步能够回答：

> “这个判断是你什么时候形成的？”
>
> “有哪些历史行为支持这个结论？”
>
> “后来你的想法有没有发生变化？”
>
> “这是你明确说过的，还是系统推断的？”

因此系统必须同时保留：

- 原始经历
- 时间关系
- 来源证据
- 结构化认知
- 不确定性
- 冲突
- 更新历史

---

# 3. 项目愿景

DigitalMe 最终希望形成：

```text
                    DIGITAL SELF

        ┌──────────── Identity ─────────────┐
        │                                    │
   Experiences                          Preferences
        │                                    │
   Projects ─────────── Memory ───────── Decisions
        │                                    │
   Relationships                        Procedures
        │                                    │
        └────────────── Agent ───────────────┘
                            │
                     Voice / Avatar
```

Memory Engine 是整个 Digital Self 的长期状态层。

未来：

- Voice Agent
- 数字人 Avatar
- Agent Tools
- 浏览器插件
- 邮件
- 日历
- GitHub
- 文件系统
- 手机
- 可穿戴设备

都共享同一套 Personal Memory。

---

# 4. v0.1 产品边界

## 4.1 v0.1 做什么

### 数据接入

支持：

- ChatGPT 数据导出 ZIP
- `conversations.json`
- 大型导出的多个 conversation JSON
- 手工导入 ChatGPT Memory Summary
- Codex `sessions/`
- Codex `archived_sessions/`
- Codex Memory 文件
- Codex 新 Session 增量发现

ChatGPT 官方目前支持通过 Data Controls 导出账户数据，其中包含聊天历史；较大的导出可能包含多个 conversation JSON。Saved Memory 与 Chat History 则属于不同的记忆机制。

Codex 当前将 session rollout 保存在类似：

```text
$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl
```

的目录中，rollout JSONL 包含 session metadata、message、tool interaction 等事件。

---

## 4.2 v0.1 不做什么

暂不实现：

- 数字人 Avatar
- TTS
- ASR
- Full Duplex Voice
- 自动操作 ChatGPT 网页
- Playwright 抓取 ChatGPT Sidebar
- 修改 Codex 自身 Memory
- 邮件/日历自动同步
- 手机端
- 多用户系统
- 云端 SaaS
- 社交网络分析
- 自动代表用户对外发送消息

这些属于后续 DigitalMe Agent / Voice / Avatar 阶段。

---

# 5. 核心设计原则

## Principle 1：Session ≠ Memory

Session 是：

> 发生过什么。

Memory 是：

> 这些经历说明了什么。

因此：

```text
Session
   ↓
Episode
   ↓
Memory Candidate
   ↓
Consolidation
   ↓
Memory
```

而不是：

```text
Session
   ↓
Embedding
   ↓
Memory
```

---

# 6. 四层记忆模型

DigitalMe 采用四层记忆体系。

```text
L0   Raw Experience

L1   Episodic Memory

L2   Semantic / Durable Memory

L3   Self Model
```

---

## 6.1 L0：Raw Experience

保存未经修改的原始数字经历。

包括：

- ChatGPT conversation
- Codex rollout
- Codex memory artifacts
- 将来的邮件
- 文件
- Git commits
- Calendar
- Voice transcript

Raw 数据：

**永不覆盖、永不由 LLM 修改。**

它是 DigitalMe 的 autobiographical archive。

---

## 6.2 L1：Episodic Memory

Episode 表示：

> 在某个时间，我围绕某件事情经历了什么。

例如：

```json
{
  "episode_id": "ep_01J...",
  "start_at": "2026-08-24T20:19:00+08:00",
  "end_at": "2026-08-24T22:00:00+08:00",
  "type": "project_exploration",
  "title": "DigitalMe 项目概念形成",
  "summary": "围绕个人数字分身讨论长期记忆、Agent、Voice 和 Avatar 的关系。",
  "projects": ["DigitalMe"],
  "decisions": [
    "DigitalMe 第一阶段优先建设 Memory Engine"
  ],
  "open_questions": [],
  "source_sessions": [
    "chatgpt:xxx"
  ]
}
```

Episode 主要描述：

- 发生了什么
- 为什么发生
- 做了什么
- 得到了什么结果

---

# 7. L2：Durable Memory

这是 DigitalMe 真正意义上的长期 Memory。

Memory 类型初步定义为：

```text
fact
preference
belief
goal
decision
decision_rule
project_state
procedure
skill
lesson
relationship_context
commitment
constraint
interest
open_loop
```

---

## 7.1 Fact

明确事实。

例如：

```text
某项目第一版使用 SQLite。
```

---

## 7.2 Preference

相对稳定的偏好。

例如：

```text
用户倾向于个人项目 MVP 优先选择较轻量的基础设施。
```

---

## 7.3 Decision

一次明确决策。

```text
DigitalMe v0.1 暂不实现 Avatar。
```

---

## 7.4 Decision Rule

多次行为形成的决策模式。

```text
对于个人实验型项目：

核心价值验证优先于基础设施完备度。
```

---

## 7.5 Project State

```text
DigitalMe:
stage = Memory Engine v0.1
current_focus = historical data ingestion
```

---

## 7.6 Procedure

实际经过验证的方法。

例如：

```text
开发 Python 项目时：

1. uv 管理环境
2. .env 保存本地配置
3. SQLite 完成 MVP
4. 必要时再迁移数据库
```

---

## 7.7 Lesson

来自失败或实验的经验。

```text
某种方案已经尝试过，没有取得预期收益，因此不应在没有新证据时重复。
```

---

## 7.8 Open Loop

非常重要的一类 Memory：

> 曾经提出，但尚未完成的事情。

例如：

```text
DigitalMe:
TODO:
- ChatGPT importer
- Codex watcher
- Memory provenance UI
```

未来 DigitalMe 可以主动回答：

> “你有哪些想做但一直没完成的事情？”

---

# 8. L3：Self Model

Self Model 不直接保存大量细节。

它是长期 Memory 的高阶压缩表示。

例如：

```text
identity/
preferences/
work_style/
technical_style/
decision_patterns/
long_term_goals/
current_focus/
important_projects/
```

Self Model 的作用主要是：

**快速恢复“这个人是谁”。**

每次 Agent 启动时，不加载几千条 Memory，而加载一个很小的：

```text
SELF.md
```

或者：

```json
{
  "identity": {},
  "current_focus": [],
  "stable_preferences": [],
  "active_projects": [],
  "decision_patterns": []
}
```

然后再根据具体问题动态检索详细 Memory。

---

# 9. Memory 最重要的属性：Provenance

每一条 Memory 必须能够回答：

> 为什么系统认为这是事实？

因此所有 Memory 必须关联 Evidence。

例如：

```text
Memory

用户在个人 MVP 项目中倾向使用轻量基础设施。

Confidence: 0.89
Status: active

Evidence
│
├── ChatGPT session A
│      “第一版数据库先用 sqlite？”
│
├── ChatGPT session B
│      对复杂基础设施表达保留态度
│
└── Codex session C
       实际实现 SQLite persistence
```

任何无法找到 Evidence 的 Memory：

**不得成为 durable memory。**

---

# 10. Memory 数据模型

核心 Memory Schema：

```json
{
  "id": "mem_01J...",
  "namespace": "global",
  "type": "preference",

  "subject": "user",

  "content": "个人项目 MVP 阶段倾向使用轻量基础设施。",

  "structured": {
    "predicate": "prefers",
    "object": "lightweight infrastructure",
    "context": "personal MVP projects"
  },

  "confidence": 0.89,
  "salience": 0.74,

  "status": "active",

  "valid_from": "2026-01-01",
  "valid_to": null,

  "first_observed_at": "2026-02-13",
  "last_confirmed_at": "2026-08-24",

  "created_at": "...",
  "updated_at": "...",

  "source_count": 4,

  "sensitivity": "personal"
}
```

---

# 11. Confidence 与 Importance 必须分离

两个概念不能混为一谈。

## Confidence

表示：

> 这条 Memory 有多可信？

---

## Salience

表示：

> 这条 Memory 对理解这个人有多重要？

例如：

```text
用户昨天午饭吃了牛肉面

confidence = 0.99
salience   = 0.03
```

而：

```text
用户明确决定长期转向某个研究方向

confidence = 0.97
salience   = 0.95
```

---

# 12. Memory 证据等级

Memory Candidate 形成时需要记录 evidence strength。

优先级：

```text
E5 用户明确要求记住

E4 用户明确陈述事实 / 决定

E3 多次一致陈述

E2 实际行为支持

E1 模型根据上下文推断

E0 无足够证据
```

E0：

直接丢弃。

E1：

原则上只能作为：

```text
hypothesis
```

不能直接写成确定事实。

---

# 13. Memory 演化模型

现实中的人会变化。

因此 DigitalMe 不允许简单：

```text
UPDATE memory
SET content = new_content
```

覆盖旧认知。

应保存时间演化。

例如：

```text
2026

prefers SQLite for MVP
        │
        ▼
2027

prefers PostgreSQL for production
but SQLite remains preferred for prototypes
```

旧 Memory：

```text
status = superseded
valid_to = ...
```

新 Memory：

```text
status = active
```

---

# 14. Memory 状态

```text
candidate
active
superseded
disputed
uncertain
archived
deleted
```

其中：

### disputed

表示证据存在冲突。

DigitalMe 必须能够说：

> “关于这一点，你过去的表达并不完全一致。”

而不是强行选择一个答案。

---

# 15. Memory Scope

每条 Memory 必须有 Scope。

```text
global

project:{project_id}

person:{person_id}

topic:{topic}

workspace:{repo}
```

例如：

```text
SQLite preference
```

可能只属于：

```text
scope = personal_projects
```

而不是：

```text
global preference
```

否则系统容易得出错误的过度泛化结论。

---

# 16. ChatGPT 数据接入

## 16.1 Bootstrap

用户手动执行官方 ChatGPT Data Export。

输入：

```text
chatgpt-export.zip
```

Importer：

```text
ChatGPTExportImporter
```

流程：

```text
ZIP
 ↓
Manifest
 ↓
conversation JSON discovery
 ↓
conversation parser
 ↓
normalized sessions/messages
 ↓
Raw Store
```

---

# 17. ChatGPT Session Normalization

统一转换成：

```json
{
  "session_id": "...",
  "source": "chatgpt",
  "title": "...",
  "created_at": "...",
  "updated_at": "...",
  "messages": []
}
```

每条 Message：

```json
{
  "message_id": "...",
  "role": "user",
  "timestamp": "...",
  "content_type": "text",
  "content": "...",
  "parent_id": "..."
}
```

需要保留 ChatGPT conversation tree。

不能假设历史 Conversation 永远是严格线性结构。

---

# 18. ChatGPT Memory 导入

ChatGPT Saved Memory 与聊天历史属于独立机制。

DigitalMe v0.1 将其视为：

```text
Imported Memory Candidate
```

而不是：

```text
Ground Truth
```

允许：

```text
Import Memory Summary
```

输入可以是：

```text
Markdown
JSON
Plain Text
```

每条 Imported Memory 都记录：

```text
source = chatgpt_memory
confidence_source = external_model_memory
```

随后重新经过：

```text
verification
deduplication
consolidation
```

---

# 19. Codex Session 接入

默认：

```text
CODEX_HOME=~/.codex
```

扫描：

```text
$CODEX_HOME/sessions/
$CODEX_HOME/archived_sessions/
```

Codex 当前 rollout 文件通常按日期目录存储 JSONL。

Importer：

```text
CodexRolloutImporter
```

---

# 20. Codex JSONL 解析

Codex rollout 可能包含：

```text
session_meta
turn_context
event_msg
response_item
tool calls
tool outputs
messages
```

DigitalMe 不复制 Codex 内部 schema。

而是使用 Adapter：

```text
Codex Schema
      ↓
Codex Adapter
      ↓
DigitalMe Canonical Schema
```

这样 Codex 后续修改格式，只需要调整 Adapter。

---

# 21. Codex 数据选择策略

不能把整个 rollout 无脑发送给 LLM。

默认规则：

| 数据 | 策略 |
|---|---|
| User message | KEEP |
| Assistant final response | KEEP |
| Agent decision | KEEP |
| reasoning summary | SELECTIVE |
| shell command | SELECTIVE |
| git diff | SUMMARIZE |
| source file dump | DROP |
| huge stdout | DROP |
| build log | SUMMARY |
| test result | KEEP SUMMARY |
| stack trace | KEEP SELECTIVE |
| `.env` | NEVER SEND |
| credentials | NEVER SEND |
| API key | NEVER SEND |
| token | NEVER SEND |

---

# 22. Codex Memory 接入

Codex 当前也具有自己的 Memory Pipeline。

官方源码显示其当前体系包含：

```text
single rollout extraction
        ↓
raw memories
        ↓
global consolidation
        ↓
MEMORY.md
memory_summary.md
```

并维护 rollout summaries 等文件。

DigitalMe **不修改 Codex Memory**。

只执行：

```text
READ ONLY
```

然后：

```text
Codex Memory
      ↓
ExternalMemoryImporter
      ↓
DigitalMe Memory Candidate
```

---

# 23. 为什么不直接复用 Codex Memory

Codex Memory 的目标主要是：

> 帮助未来 Coding Agent 更有效地工作。

DigitalMe 的目标则是：

> 理解这个人的长期经历、自我、项目、选择和行为。

两个目标不同。

因此：

```text
Codex Memory
    =
DigitalMe 的一个高价值 Source

而不是

DigitalMe Memory Database
```

---

# 24. Ingestion Pipeline

完整流程：

```text
              DATA SOURCES
                   │
       ┌───────────┴───────────┐
       │                       │
    ChatGPT                  Codex
       │                       │
       └───────────┬───────────┘
                   ▼
              Collector
                   ▼
             Raw Archive
                   ▼
              Normalizer
                   ▼
           Privacy / Secret
               Filter
                   ▼
              Sessions
                   ▼
          Episode Extractor
                   ▼
          Memory Extractor
                   ▼
         Memory Candidates
                   ▼
              Resolver
             ↙    ↓    ↘
          Merge Conflict New
             \     │    /
              Consolidator
                   ▼
             Durable Memory
                   ▼
              Self Model
```

---

# 25. Raw Archive

推荐：

```text
data/
└── raw/
    ├── chatgpt/
    │   └── {artifact_hash}/
    │
    └── codex/
        └── {session_id}/
```

所有文件根据：

```text
SHA-256
```

生成内容指纹。

作用：

- 去重
- 数据完整性
- 可追溯
- 幂等导入

---

# 26. 幂等性

同一个 ChatGPT Export 导入十次：

结果必须和导入一次一致。

同一个 Codex rollout 被 watcher 检测十次：

不得产生十条 Session。

核心键：

```text
source
external_id
content_hash
```

---

# 27. 数据库设计

v0.1 使用 SQLite。

核心表：

```text
sources

artifacts

sessions

messages

episodes

entities

projects

memory_candidates

memories

memory_evidence

memory_relations

embeddings

ingestion_jobs

memory_revisions
```

---

# 28. memory_evidence

这是整个系统最重要的表之一。

```text
memory_id
source_type
session_id
message_id
episode_id
artifact_id

evidence_type
evidence_strength

quote_start
quote_end

created_at
```

Memory 与原始记录建立显式关系。

---

# 29. memory_revisions

用户修改 Memory 时：

不要直接覆盖。

保存：

```text
revision 1
revision 2
revision 3
```

能够回答：

> “这条记忆为什么发生变化？”

---

# 30. Embedding 的定位

Embedding：

**不是 Memory Database。**

Embedding 只是：

> Retrieval Index。

建议 Embedding 三类对象：

```text
episodes

memories

selected messages
```

而不是默认 Embedding 所有 Codex stdout。

---

# 31. Retrieval Engine

查询：

```text
“我之前为什么不继续做那个 EEG 对比学习方向？”
```

处理流程：

```text
Query
 ↓
Intent Analysis
 ↓
Entity / Project Recognition
 ↓
Scope Filter
 ↓
Time Filter
 ↓
Hybrid Retrieval
 ↓
Reranker
 ↓
Memory Pack
 ↓
LLM
```

---

# 32. Hybrid Retrieval

组合：

```text
FTS5 / BM25
+
Vector Search
+
Entity Match
+
Time
+
Memory Importance
+
Confidence
```

不要只用向量相似度。

---

# 33. Memory Pack

LLM 最终不应该看到：

```text
全部 Memory
```

而应该收到：

```text
Memory Pack
```

例如：

```json
{
  "query": "...",

  "self_context": [],

  "relevant_memories": [],

  "episodes": [],

  "active_project_state": [],

  "contradictions": [],

  "open_loops": []
}
```

一般控制在少量高价值信息。

---

# 34. 两级 Retrieval

## Level 1：Self Model

先判断：

> 这个问题是否需要个人 Context？

---

## Level 2：Detailed Memory

需要时再检索：

```text
Memory
Episode
Raw Evidence
```

形成 progressive disclosure：

```text
Self Summary
     ↓
Memory
     ↓
Episode
     ↓
Original Message
```

这个设计与当前 Codex Memory 使用 summary → MEMORY → rollout evidence 的渐进式检索思想也存在相似之处。

---

# 35. Memory Extraction

每个 Episode 进入：

```text
MemoryExtractor
```

输出严格 JSON。

例如：

```json
{
  "candidates": [
    {
      "type": "decision",
      "content": "DigitalMe v0.1 优先建设 Memory Engine。",
      "scope": "project:digitalme",
      "confidence": 0.98,
      "evidence_strength": "E4",
      "temporal": {
        "valid_from": "2026-08-24"
      }
    }
  ]
}
```

---

# 36. Memory Resolver

Memory Candidate 不直接写入 Durable Memory。

首先经过 Resolver：

```text
candidate
   │
   ├─ same memory ─────→ reinforce
   │
   ├─ more specific ───→ refine
   │
   ├─ newer version ───→ supersede
   │
   ├─ contradictory ───→ disputed
   │
   └─ genuinely new ───→ create
```

---

# 37. Memory Consolidation

定期执行：

```text
Memory Consolidator
```

主要处理：

- 重复
- 泛化
- 冲突
- 长期演化
- 低价值 Memory 衰减
- 重要 Memory 晋升
- Self Model 更新

注意：

**Memory Consolidation 不删除 Raw Experience。**

---

# 38. Secret Filter

Codex 数据尤其容易出现：

```text
API_KEY
PASSWORD
TOKEN
PRIVATE_KEY
DATABASE_URL
COOKIE
Authorization
SSH key
```

所以：

```text
Raw data
   ↓
Secret Scanner
   ↓
Redacted View
   ↓
LLM
```

任何外部模型只能看到：

```text
Redacted View
```

不能直接看到 Raw。

---

# 39. Sensitivity

每个 Memory 标记：

```text
public
personal
sensitive
secret
```

`secret`：

永远不得进入模型 Prompt。

`sensitive`：

默认 local-only，除非用户显式允许对应 Provider。

---

# 40. Local-first

v0.1 默认：

```text
localhost
```

数据：

```text
SQLite
+
local filesystem
```

不设计账户系统。

不设计云同步。

不设计多租户。

---

# 41. LLM Provider Abstraction

Memory Engine 不绑定某一个模型。

定义统一：

```text
LLMProvider

extract()
summarize()
resolve()
consolidate()
answer()
```

可以实现：

```text
OpenAIProvider
LocalProvider
OtherProvider
```

这样未来可以：

- 云端高能力模型做复杂 consolidation
- 本地模型做隐私敏感 extraction

---

# 42. Embedding Provider

同样抽象：

```text
EmbeddingProvider
```

支持：

```text
CloudEmbeddingProvider
LocalEmbeddingProvider
```

---

# 43. 后端技术栈

推荐：

```text
Python 3.12+
uv

FastAPI
Pydantic v2
SQLAlchemy 2
Alembic

SQLite
FTS5

sqlite-vec

watchfiles

httpx

pytest
```

v0.1 不引入：

```text
Celery
Kafka
Redis
PostgreSQL
Kubernetes
```

除非实际需求证明有必要。

---

# 44. 前端技术栈

```text
Next.js
React
TypeScript
```

前端暂时只有 Memory Management UI。

---

# 45. Repository Structure

建议：

```text
digitalme/
│
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
│
├── backend/
│   └── digitalme/
│       │
│       ├── api/
│       │
│       ├── config/
│       │
│       ├── db/
│       │
│       ├── models/
│       │
│       │
│       ├── ingestion/
│       │   ├── chatgpt/
│       │   ├── codex/
│       │   └── common/
│       │
│       ├── privacy/
│       │
│       ├── episodes/
│       │
│       ├── memory/
│       │   ├── extractor.py
│       │   ├── resolver.py
│       │   ├── consolidator.py
│       │   └── scoring.py
│       │
│       ├── retrieval/
│       │
│       ├── providers/
│       │   ├── llm/
│       │   └── embedding/
│       │
│       └── services/
│
├── frontend/
│
├── data/
│   ├── raw/
│   ├── cache/
│   └── digitalme.db
│
├── prompts/
│   ├── episode_extraction.md
│   ├── memory_extraction.md
│   └── memory_consolidation.md
│
└── tests/
    ├── fixtures/
    ├── ingestion/
    ├── memory/
    └── retrieval/
```

---

# 46. CLI

建议同时提供 CLI：

```text
digitalme ingest chatgpt <export.zip>

digitalme ingest chatgpt-memory <memory.md>

digitalme ingest codex

digitalme watch codex

digitalme sessions list

digitalme memories list

digitalme memories inspect <id>

digitalme memories rebuild

digitalme ask "..."
```

这使开发阶段不依赖 Web UI。

---

# 47. API

## Import ChatGPT

```text
POST /api/v1/ingest/chatgpt
```

---

## Scan Codex

```text
POST /api/v1/ingest/codex/scan
```

---

## Sessions

```text
GET /api/v1/sessions

GET /api/v1/sessions/{id}
```

---

## Episodes

```text
GET /api/v1/episodes

GET /api/v1/episodes/{id}
```

---

## Memories

```text
GET    /api/v1/memories

GET    /api/v1/memories/{id}

PATCH  /api/v1/memories/{id}

DELETE /api/v1/memories/{id}
```

---

## Evidence

```text
GET /api/v1/memories/{id}/evidence
```

---

## Retrieval

```text
POST /api/v1/retrieve
```

---

## Ask

```text
POST /api/v1/ask
```

---

# 48. Web UI

v0.1 需要五个核心页面。

## Dashboard

显示：

```text
Sessions       1843
Episodes       924
Memories       376
Open Loops      31

ChatGPT █████████
Codex   ██████
```

---

# 49. Timeline

能够看到：

```text
2026-08

DigitalMe
│
├─ 项目概念形成
├─ Memory Engine 定义
└─ 技术选型

EEG Research
│
├─ ...
└─ ...
```

时间线本身就是 Digital Self 非常重要的可视化。

---

# 50. Memory Explorer

支持：

```text
Search

Type

Project

Time

Status

Confidence

Sensitivity
```

---

# 51. Memory Inspector

重点页面：

```text
┌──────────────────────────────────┐
│ Memory                           │
│                                  │
│ 个人 MVP 倾向轻量基础设施。       │
│                                  │
│ Type        Preference           │
│ Confidence  0.89                 │
│ Salience    0.74                 │
│ Scope       Personal Project     │
│ Status      Active               │
│                                  │
│ Evidence                         │
│                                  │
│ ChatGPT · xxx                    │
│ Codex · xxx                      │
│                                  │
│ History                          │
│ Revision 1                       │
│ Revision 2                       │
│                                  │
│ [Edit] [Dispute] [Delete]        │
└──────────────────────────────────┘
```

---

# 52. Session Viewer

用户可以从：

```text
Memory
```

逐级回溯：

```text
Memory
 ↓
Episode
 ↓
Session
 ↓
Original Message
```

这是 DigitalMe 的 Explainability。

---

# 53. Memory Control

用户永远拥有最高权限。

用户可以：

```text
confirm

edit

merge

split

mark incorrect

mark outdated

delete

pin

change scope

change sensitivity
```

LLM 不能凌驾于用户编辑结果。

---

# 54. 用户修改优先级

证据等级最高：

```text
USER_CONFIRMED
```

用户明确修改后的 Memory：

自动提升 evidence strength。

模型以后不得凭普通推断覆盖。

---

# 55. Codex Continuous Sync

Codex 支持本地增量同步。

```text
watchfiles
   ↓
CODEX_HOME/sessions
   ↓
new / modified rollout
   ↓
incremental parse
   ↓
session update
```

读取：

**READ ONLY。**

DigitalMe 永远不修改 rollout。

---

# 56. ChatGPT Continuous Sync

v0.1：

不做网页自动抓取。

采用：

```text
Periodic Export
       ↓
Import
       ↓
Hash
       ↓
Deduplicate
       ↓
Incremental Update
```

以后可扩展：

```text
Browser Extension
```

但不作为核心依赖。

---

# 57. Project Recognition

Memory Engine 需要识别：

```text
Project
```

例如同一项目可能出现多个名字。

因此：

```text
projects
```

至少包含：

```text
id
canonical_name
aliases
status
created_at
updated_at
```

---

# 58. Entity System

同样需要：

```text
entities
```

可以代表：

```text
person
company
project
technology
place
organization
concept
```

目的不是构建大型 Knowledge Graph。

而是解决：

> 不同 Session 中的“这个项目”“它”“BridgeMIL”是不是同一个东西？

---

# 59. Personal Knowledge Graph

v0.1 暂时只建立轻量关系：

```text
Memory
  ├─ ABOUT → Project
  ├─ INVOLVES → Person
  ├─ SUPPORTS → Memory
  ├─ CONTRADICTS → Memory
  ├─ SUPERSEDES → Memory
  └─ DERIVED_FROM → Episode
```

不引入 Neo4j。

SQLite 足够。

---

# 60. Memory Decay

不是所有记忆都应该永久保持高权重。

定义：

```text
retrieval_priority
```

受以下因素影响：

```text
salience
recency
frequency
confidence
query relevance
scope relevance
user pinning
```

但：

**Decay 只降低检索优先级，不删除历史。**

---

# 61. Project State 不做普通 Decay

例如：

```text
项目已经暂停
```

虽然很久以前发生，但它仍可能是当前事实。

因此 Memory 类型决定 Temporal Policy。

---

# 62. Evaluation Dataset

正式开发时建立：

```text
tests/golden/
```

手工标注一小批 Session：

```text
Session
 ↓
Expected Episodes
 ↓
Expected Memories
 ↓
Expected Evidence
```

作为 Memory Pipeline regression test。

---

# 63. 核心评估指标

## Ingestion

```text
Import Completeness

Parse Error Rate

Duplicate Rate

Idempotency
```

---

## Memory

```text
Memory Precision

Evidence Correctness

Duplicate Memory Rate

Contradiction Detection

Temporal Correctness
```

---

## Retrieval

```text
Recall@K

Evidence Recall

Project Scope Accuracy

Temporal Accuracy
```

---

# 64. 最重要的质量指标

不是：

```text
Memory 数量越多越好
```

而是：

```text
Memory Precision
```

宁可：

```text
300 条高价值记忆
```

也不要：

```text
30,000 条聊天摘要
```

---

# 65. v0.1 Acceptance Test

DigitalMe Memory Engine v0.1 完成时必须通过以下场景。

---

## Case 1：历史导入

导入完整 ChatGPT Export。

能够浏览：

```text
Session → Messages
```

---

## Case 2：Codex 导入

扫描：

```text
CODEX_HOME
```

能够识别历史 Codex sessions。

---

## Case 3：幂等

同一个数据源重新导入：

```text
duplicate session = 0
```

---

## Case 4：Episode

系统能把一个长 Session 提炼成少量有意义 Episode。

---

## Case 5：Memory

Episode 能进一步产生：

```text
Decision
Preference
Project State
Procedure
Lesson
Open Loop
```

等 Memory。

---

## Case 6：Provenance

任意 Memory：

必须至少能够回到：

```text
Session
```

最好能回到：

```text
Message
```

---

## Case 7：Conflict

历史出现：

```text
A
↓
后来改变为 B
```

不能覆盖历史。

必须：

```text
A superseded
B active
```

---

## Case 8：User Override

用户编辑 Memory 后：

后续 consolidation 不得重新恢复被用户明确否定的版本。

---

## Case 9：Secret Protection

包含：

```text
API key
Token
Password
.env
```

的 Codex 内容不得进入外部 LLM 请求。

---

## Case 10：Personal Question

用户询问：

> “过去一年我主要在研究什么？”

系统能够：

1. 找到相关 Memory
2. 找到相关 Episode
3. 建立时间线
4. 引用原始 Session
5. 区分事实与推断

---

# 66. v0.1 最关键 Demo

Demo 不应该是：

> “搜索以前的聊天。”

而应该是：

用户导入 ChatGPT + Codex 后询问：

> **过去一年我的技术兴趣发生了什么变化？**

DigitalMe 返回：

```text
早期
│
├─ A
├─ B
└─ C

         ↓

中期
│
├─ 逐渐减少 X
└─ 开始关注 Y

         ↓

近期
│
├─ Y
├─ Z
└─ DigitalMe
```

并说明：

```text
哪些只是讨论

哪些实际形成了项目

哪些项目被放弃

哪些方向持续存在

哪些判断发生过变化
```

最后每个核心判断：

可以点击进入：

```text
Memory
 ↓
Evidence
 ↓
Original Session
```

---

# 67. 第二个核心 Demo

用户问：

> **我有哪些反复提过、但一直没有真正完成的项目？**

系统检索：

```text
Open Loops
+
Project State
+
Episodes
+
Codex Implementation Evidence
```

区分：

```text
想过

讨论过

写过方案

写过代码

真正运行过

完成过
```

这是普通 RAG 很难可靠完成的事情。

---

# 68. 第三个核心 Demo

用户问：

> **我做技术决策时有什么稳定模式？**

系统不是简单搜索。

而是基于：

```text
multiple decisions
        ↓
pattern mining
        ↓
Decision Rule
```

形成：

```text
你的历史行为显示：

在 X 类型项目中通常优先 A；
在 Y 情况下则更倾向 B。

这个判断来自 7 次项目决策，
其中 5 次支持，2 次例外。
```

这才开始真正出现：

**Digital Self。**

---

# 69. 开发阶段划分

## M0 — Foundation

完成：

```text
project skeleton
SQLite
models
migration
CLI
config
```

---

## M1 — Historical Archive

完成：

```text
ChatGPT importer

Codex importer

Raw Store

Session Browser
```

此时：

只解决“我过去发生过什么”。

---

## M2 — Episodic Memory

完成：

```text
Session segmentation

Episode extraction

Timeline
```

此时解决：

> “过去发生了哪些事情？”

---

## M3 — Durable Memory

完成：

```text
Memory Candidate

Resolver

Consolidator

Evidence

Revision

Conflict
```

此时解决：

> “这些经历说明了什么？”

---

## M4 — Retrieval

完成：

```text
FTS

Embedding

Hybrid Search

Memory Pack

Ask
```

---

## M5 — Memory UI

完成：

```text
Dashboard

Timeline

Memory Explorer

Memory Inspector

Evidence Viewer
```

---

# 70. v0.2

v0.2 可以开始加入：

```text
automatic project tracking

Git repository ingestion

Git commit history

GitHub

local files

browser history selective ingestion

PDF / document knowledge
```

---

# 71. v0.3

加入：

```text
Email

Calendar

Contacts

personal event timeline
```

DigitalMe 开始了解：

> 最近实际发生了什么。

---

# 72. v0.4

加入：

```text
Realtime Voice
ASR
TTS
```

Memory Engine 不变。

只增加新的 Interaction Interface。

---

# 73. v0.5

加入：

```text
Digital Avatar
```

最终：

```text
Face
Voice
Agent
Memory
Self
```

组合成真正的数字分身。

---

# 74. 项目的核心技术判断

DigitalMe 必须坚持以下五条原则：

### 1. Raw Experience 永久保留

任何模型生成的 Summary 都不能替代原始历史。

### 2. Memory 必须有 Evidence

无法追溯的 Memory 不可信。

### 3. Memory 允许变化

人不是静态配置文件。

### 4. Retrieval 与 Storage 分离

Embedding 是索引，不是记忆本身。

### 5. 用户拥有最终解释权

模型只能提出：

```text
Memory Candidate
```

最终的 Digital Self：

属于用户本人。

---

# 75. 一句话定义

**DigitalMe Memory Engine 是一个 Local-first、Evidence-grounded、Temporal-aware 的个人长期记忆系统，将 ChatGPT、Codex 等数字经历转化为可追溯、可演化、可检索、可由用户控制的 Digital Self Memory。**

---

# 76. v0.1 Definition of Done

当以下问题第一次能被系统可靠回答：

> **“根据我过去真实做过和说过的事情，你认为我是怎样做技术决策的？请告诉我证据，而且区分哪些是我明确说过的、哪些只是你的推断。”**

并且 DigitalMe 能够：

```text
给出结论
   +
时间线
   +
置信度
   +
反例
   +
原始 Session Evidence
```

**DigitalMe Memory Engine v0.1 即完成。**