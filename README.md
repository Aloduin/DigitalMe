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
```

Imports are immutable at the Raw Store boundary and idempotent in the canonical database. The ZIP
reader rejects unsafe paths, encrypted members, oversized members and suspicious compression ratios.
Normalized messages also receive a deterministic `redacted_text` view with auditable source offsets.
Existing rows from older databases remain `unclassified` until they are safely re-imported; provider
integrations must never fall back from a missing redacted view to raw normalized content.

Quality checks:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

Copy `.env.example` to `.env` for optional DeepSeek configuration. Never commit `.env` or local
DigitalMe data.
