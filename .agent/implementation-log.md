# DigitalMe Implementation Log

## 2026-08-24 — Phase 0 Foundation

Completed:

- FND-001: configured Python 3.13 project metadata, runtime/dev dependencies and `uv.lock`.
- FND-002: added typed settings, optional DeepSeek configuration, installable package, CLI and FastAPI health endpoint.
- FND-003: added SQLite engine policy, core archive ORM models, Alembic environment and reversible initial migration.
- Security baseline: `.env` and local data are ignored; `.env.example` contains no credential.
- Quality baseline: Ruff formatting/lint, strict mypy and pytest are configured.

Core tables introduced:

- `sources`
- `artifacts`
- `sessions`
- `messages`
- `ingestion_jobs`
- `ingestion_errors`

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -vv` — 4 passed
- `uv run digitalme --version` — `0.1.0`

Issue found and fixed during verification:

- Executing SQLite `PRAGMA foreign_keys=ON` in Alembic opened an implicit transaction. SQLite kept the DDL but rolled back the Alembic version row when the connection closed, making downgrade a no-op. The migration environment now commits the PRAGMA transaction before Alembic starts its migration transaction. The test verifies `upgrade → downgrade → upgrade`.

## 2026-08-24 — Phase 1 ChatGPT Archive Slice

Completed:

- ARC-001: atomic, content-addressed Raw Artifact Store using SHA-256.
- ARC-002: strict, versioned Canonical Session/Message Pydantic contracts.
- ARC-003: persisted ingestion job lifecycle and safe failure summaries.
- ARC-004: in-place ChatGPT ZIP discovery with path, encryption, size and compression-ratio guards.
- ARC-005: ChatGPT conversation-tree adapter preserving empty nodes, branches, timestamps, roles, locators and parse warnings.
- Idempotent persistence: repeated imports reuse artifacts and update existing sessions/messages without duplicates.
- CLI: `digitalme ingest chatgpt` and `digitalme sessions list`.

No model provider is called by this slice; imported content remains local.

## 2026-08-25 — Phase 1 Privacy Boundary

Completed:

- ARC-008 foundation: deterministic secret scanning for credential assignments, authorization
  headers, URL credentials, private keys, known token formats and high-entropy candidates.
- Added immutable-derived `redacted_text`, original-text redaction spans and message sensitivity.
- Added path denylist helpers and a provider policy gate: secret/unclassified content is blocked;
  sensitive content requires a local provider.
- Integrated redaction into ChatGPT imports and exposed aggregate redaction counts in CLI output.
- Added a reversible Alembic migration. Pre-existing messages remain `unclassified` with no redacted
  view until re-imported, preventing consumers from silently falling back to unsafe text.

Verification:

- `uv run ruff format --check backend tests`
- `uv run ruff check backend tests`
- `uv run mypy`
- `uv run pytest -q` — 21 passed

No provider call was added. Raw artifacts and normalized source text remain unchanged for provenance;
only the derived redacted view is eligible for future provider-facing pipelines.

## 2026-08-25 — Phase 1 Archive Browsing

Completed:

- ARC-009 read side: shared `ArchiveQueryService` used by CLI and FastAPI rather than duplicated
  persistence queries.
- Added paginated Session listing with source/time filters and Session detail with deterministic
  message ordering.
- Added paginated ingestion Job listing/filtering and safe Job inspection.
- Added CLI commands: `sessions show`, `jobs list`, and `jobs inspect`.
- Added API endpoints: `GET /api/v1/sessions`, `GET /api/v1/sessions/{id}`,
  `GET /api/v1/jobs`, and `GET /api/v1/jobs/{id}`.
- Session read models intentionally exclude `normalized_text`; unclassified legacy messages return a
  null redacted view instead of falling back to source text.
- Import exception summaries now pass through deterministic redaction before persistence and API
  exposure.

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 23 passed

The HTTP import command and asynchronous job submission semantics remain a separate ARC-009 slice.

## 2026-08-25 — Phase 1 Asynchronous HTTP Import

Completed:

- Completed the ARC-009 HTTP write side with `POST /api/v1/ingest/chatgpt`.
- The endpoint accepts a raw ZIP/octet-stream body, streams it to a server-generated incoming file,
  enforces both declared and observed byte limits, and rejects unsupported or empty bodies.
- Refactored `ChatGPTImporter` into explicit `create_job` and atomic `run_job` operations while
  preserving the synchronous CLI behavior.
- Added deterministic `pending → running → completed | completed_with_warnings | failed` transitions
  and prevented the same Job from being claimed twice.
- Returns `202 Accepted`, Job ID, detail URL and `Location`; existing Job APIs expose progress and
  redacted failure summaries.
- Background processing reuses the same importer and removes request-owned temporary files on both
  successful and failed imports.

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 28 passed

Current operational boundary:

- Execution uses FastAPI in-process background tasks. A process crash can leave a pending/running Job
  and incoming file; restart recovery and a durable worker are still part of ARC-003 follow-up work.

## 2026-08-25 — Phase 1 Codex Prototype Slice

Completed:

- ARC-006 prototype discovery scans `sessions/` and `archived_sessions/` for rollout JSONL files.
- ARC-007 prototype adapter streams JSONL, preserves session metadata and line locators, imports
  user/assistant messages, and tolerates malformed lines and unknown outer event types.
- Prefers `response_item` messages and suppresses duplicate lightweight `event_msg` copies.
- Added idempotent artifact/session/message persistence with the existing redaction boundary.
- Added one-shot CLI command: `digitalme ingest codex [--codex-home PATH]`.

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 31 passed

Prototype boundary:

- No continuous watcher, tool-output summarization, Codex Memory import or HTTP scan endpoint yet.
- Tool calls, file dumps and large command output remain only in immutable Raw artifacts.

## 2026-08-25 — Browser Prototype

Completed:

- Added a dependency-free browser UI at `/` on the existing FastAPI process.
- Connected ChatGPT ZIP upload, recent ingestion Jobs, ChatGPT/Codex Session filtering and redacted
  message inspection into one demonstrable flow.
- Dynamic source content is rendered with DOM `textContent`, never `innerHTML`.
- Added a restrictive prototype Content Security Policy and responsive single-page layout.

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 32 passed

Prototype boundary:

- No frontend framework, bundler, authentication, pagination controls or production asset pipeline.

## 2026-08-27 — Ingestion Restart Recovery

Completed:

- Finished the ARC-003 restart recovery slice for HTTP ChatGPT imports.
- Application startup now discovers non-terminal jobs and replays them serially.
- Jobs interrupted before archival resume from their server-named incoming file; jobs interrupted
  after archival resume from the immutable Raw Store artifact without deleting it.
- Interrupted `running` jobs are atomically reset to `pending`, increment `retry_count`, and retain
  their checkpoint. Missing, escaping or symlinked incoming inputs fail with a bounded safe summary.
- Accepted HTTP imports use managed worker threads so API event-loop progress does not depend on
  cross-thread completion callbacks; lightweight read endpoints use async entry points.

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 35 passed

Current operational boundary:

- Recovery assumes one local application instance owns the SQLite database and incoming directory.
- A separate durable queue, multi-process lease/heartbeat and cancellation remain future work.

## 2026-08-27 — Episode MVP Slice

Completed:

- Added versioned `episodes` and `episode_messages` persistence with a reversible Alembic migration.
- Implemented deterministic Session segmentation using selected ChatGPT branches, 90-minute gaps,
  explicit new-topic markers and a 24-message upper bound.
- Rebuilding the same pipeline version is idempotent; a different version can coexist for later
  extraction comparisons.
- Every Episode is linked to ordered Message evidence. Only redacted views participate, so legacy
  unclassified content does not silently cross the privacy boundary.
- Added Episode rebuild/list/detail commands and API endpoints, plus browser generation and evidence
  inspection controls.

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 37 passed

MVP boundary:

- Episodes currently have deterministic titles and `segmented` status; semantic summary, decisions,
  open questions and Memory Candidate extraction remain the next value slice.
- No external model call is made by segmentation.

## 2026-08-27 — Evidence-linked Memory Candidate MVP

Completed:

- Added DeepSeek JSON-mode support behind an explicit, replaceable `JsonProvider` boundary.
- Added strict Episode extraction and Memory Candidate contracts covering type, scope, confidence,
  salience, evidence strength and source Message IDs.
- Provider input is assembled only from eligible redacted views. Secret/unclassified content is
  excluded before the request; a fully blocked Episode fails without making a provider call.
- Added semantic Episode fields, Memory Candidate persistence and redacted quote snapshots linked to
  Message foreign keys through a reversible migration.
- Invalid/out-of-range evidence rejects the whole extraction transaction. E1 becomes `hypothesis`;
  stronger candidates remain reviewable until explicitly confirmed or rejected.
- Re-extraction preserves confirmed/rejected content, and Episode rebuild refuses to cascade-delete
  user-governed Candidate state.
- Added CLI/API/browser flows for extract, list, inspect, confirm and reject.

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 44 passed

MVP boundary:

- There is no automated resolver, consolidation, cross-Episode deduplication, FTS retrieval or Ask
  service yet. Confirmed Candidate status is the current user-governed durable-memory boundary.

## 2026-08-27 — Confirmed Memory Retrieval and Ask MVP

Completed:

- Added deterministic local retrieval over user-confirmed, evidence-linked Memory Candidates only,
  with English token filtering, CJK bigram matching and bounded scoring across content, type, scope
  and Episode context.
- Candidate content/type/scope must match before Episode context can improve rank, preventing a shared
  Episode summary from admitting unrelated Memories.
- Added an explicit Ask action that sends a bounded Memory Pack containing only provider-eligible
  confirmed Memories and their redacted evidence snapshots.
- Added a strict structured answer contract. Citation IDs outside the exact provider input reject the
  entire answer; no relevant eligible result fails before any provider call.
- Added CLI, API and browser flows for local retrieval, evidence-grounded Ask and clickable Memory
  citations.

Verification:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest -q` — 49 passed

MVP boundary:

- Retrieval is an in-process lexical scan of at most 2,000 confirmed Memories, not FTS5 or vector
  search. Ask responses are not persisted, and there is no reranker, timeline synthesis, contradiction
  analysis or multi-hop retrieval yet.
