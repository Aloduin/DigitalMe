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
