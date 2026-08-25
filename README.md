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

Import an official ChatGPT data export and browse the normalized sessions:

```bash
uv run digitalme ingest chatgpt /path/to/chatgpt-export.zip
uv run digitalme sessions list
uv run digitalme sessions show <session-id>
uv run digitalme jobs list
uv run digitalme jobs inspect <job-id>
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
background task. Use the Job endpoint to inspect completion or a redacted failure summary. A later
worker/recovery slice will make queued execution durable across application restarts.

Quality checks:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

Copy `.env.example` to `.env` for optional DeepSeek configuration. Never commit `.env` or local
DigitalMe data.
