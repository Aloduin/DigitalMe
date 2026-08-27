# DigitalMe

DigitalMe Memory Engine is a local-first, evidence-grounded personal memory system.

The project is currently implementing the v0.1 foundation and historical archive described in
[`docs/DigitalMe Memory Engine v0.1 项目设计文档.md`](docs/DigitalMe%20Memory%20Engine%20v0.1%20项目设计文档.md).

## Development

Python environments and dependencies are managed exclusively with `uv`.

```bash
uv sync
uv run digitalme --help
uv run digitalme db upgrade
uv run uvicorn digitalme.api.app:create_app --factory --reload
```

Open `http://127.0.0.1:8000/` for the dependency-free prototype UI. It supports local ChatGPT ZIP
upload, ingestion Job status, source-filtered ChatGPT/Codex Sessions and redacted message viewing.

Import an official ChatGPT data export and browse the normalized sessions:

```bash
uv run digitalme ingest chatgpt /path/to/chatgpt-export.zip
uv run digitalme ingest codex
uv run digitalme sessions list
uv run digitalme sessions show <session-id>
uv run digitalme jobs list
uv run digitalme jobs inspect <job-id>
uv run digitalme episodes rebuild
uv run digitalme episodes list
uv run digitalme episodes show <episode-id>
uv run digitalme memories extract <episode-id>
uv run digitalme memories list
uv run digitalme memories show <candidate-id>
uv run digitalme memories confirm <candidate-id>
uv run digitalme retrieve "MVP first"
uv run digitalme ask "Why did I choose the MVP first?"
```

Imports are immutable at the Raw Store boundary and idempotent in the canonical database. The ZIP
reader rejects unsafe paths, encrypted members, oversized members and suspicious compression ratios.
Normalized messages also receive a deterministic `redacted_text` view with auditable source offsets.
Existing rows from older databases remain `unclassified` until they are safely re-imported; provider
integrations must never fall back from a missing redacted view to raw normalized content.

The local API exposes the same bounded read service:

```text
GET /api/v1/sessions
GET /api/v1/sessions/{session_id}
GET /api/v1/jobs
GET /api/v1/jobs/{job_id}
POST /api/v1/episodes/rebuild
GET /api/v1/episodes
GET /api/v1/episodes/{episode_id}
POST /api/v1/episodes/{episode_id}/extract
GET /api/v1/memories
GET /api/v1/memories/{candidate_id}
PATCH /api/v1/memories/{candidate_id}
POST /api/v1/retrieve
POST /api/v1/ask
```

List endpoints support pagination and filters. Session detail responses intentionally omit
`normalized_text`; only the safe derived view and source locators are returned.

Queue a ChatGPT export by sending the ZIP as the raw request body:

```bash
curl --request POST \
  --header "Content-Type: application/zip" \
  --data-binary @/path/to/chatgpt-export.zip \
  http://127.0.0.1:8000/api/v1/ingest/chatgpt
```

The endpoint returns `202 Accepted`, a Job ID and a `Location` header. Uploads are streamed to a
server-named temporary file, bounded by `DIGITALME_MAX_UPLOAD_BYTES`, and processed by an in-process
background task. Use the Job endpoint to inspect completion or a redacted failure summary. On
startup, the application resumes pending/interrupted jobs from the trusted incoming file or the
immutable Raw Store artifact, increments the retry count for interrupted work, and safely fails jobs
whose checkpoint input is unavailable. Execution remains an in-process, single-application worker;
an external durable queue is outside the current local prototype boundary.

The Codex prototype performs a one-shot, read-only scan of `sessions/` and `archived_sessions/` under
`DIGITALME_CODEX_HOME` (default `~/.codex`). It imports user/assistant text with JSONL line locators,
skips tool payloads and large logs, tolerates malformed lines, and does not start a filesystem watcher.

The Episode MVP turns imported Sessions into deterministic, versioned conversation segments. It
follows the selected ChatGPT branch, splits on a 90-minute gap, explicit new-topic markers or a
24-message bound, and links every Episode to its source Message rows. Only `redacted_text` is eligible;
unclassified legacy messages are excluded. Use the browser's “从 Sessions 生成” action or the CLI/API
commands above to rebuild and inspect the evidence chain.

Semantic extraction is an explicit, user-triggered MVP action. With `API_KEY`, `API_BASE_URL` and
optional `DEEPSEEK_MODEL` configured, it sends only provider-eligible `redacted_text` to DeepSeek JSON
mode, validates the returned Episode/Candidate contract, and rejects evidence IDs outside the actual
input. Secret and unclassified Messages are excluded before the request. Extracted Candidates remain
reviewable until the user confirms or rejects them; each Candidate retains redacted Message evidence.
No model call occurs during import, Episode segmentation, browsing or application startup.

The retrieval MVP searches only user-confirmed Memory Candidates that retain linked Evidence.
`retrieve` uses deterministic local lexical ranking over candidate content, type and scope, with
semantic Episode fields contributing only to ranking; it never calls a model. `ask` is a separate
explicit action that sends at most a small, provider-eligible Memory Pack with redacted evidence
quotes. The structured response is rejected if it cites a Memory ID outside that exact pack. The
browser, CLI and API all expose the same flow. FTS5, vector search, reranking and saved question history
are intentionally deferred.

Quality checks:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

Copy `.env.example` to `.env` for optional DeepSeek configuration. Never commit `.env` or local
DigitalMe data.
