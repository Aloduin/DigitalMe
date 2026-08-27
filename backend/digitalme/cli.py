"""DigitalMe command-line interface."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from alembic import command
from alembic.config import Config

from digitalme import __version__
from digitalme.archive import ArchiveQueryService
from digitalme.config import get_settings
from digitalme.db.session import create_engine, create_session_factory
from digitalme.episodes import EpisodeService
from digitalme.ingestion.chatgpt import ChatGPTImporter
from digitalme.ingestion.codex import CodexImporter
from digitalme.ingestion.common import ArtifactStore
from digitalme.memory import ExtractionValidationError, MemoryService
from digitalme.privacy import ProviderPolicyError
from digitalme.providers import (
    DeepSeekJsonProvider,
    ProviderConfigurationError,
    ProviderResponseError,
)
from digitalme.retrieval import (
    NoRelevantMemoriesError,
    RetrievalService,
    RetrievalValidationError,
)

app = typer.Typer(help="DigitalMe Memory Engine")
db_app = typer.Typer(help="Manage the local database")
ingest_app = typer.Typer(help="Import historical source data")
sessions_app = typer.Typer(help="Browse canonical sessions")
jobs_app = typer.Typer(help="Inspect ingestion jobs")
episodes_app = typer.Typer(help="Build and browse episodic memory")
memories_app = typer.Typer(help="Extract and govern evidence-linked memories")
app.add_typer(db_app, name="db")
app.add_typer(ingest_app, name="ingest")
app.add_typer(sessions_app, name="sessions")
app.add_typer(jobs_app, name="jobs")
app.add_typer(episodes_app, name="episodes")
app.add_typer(memories_app, name="memories")


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(project_root / "alembic.ini")
    config.set_main_option(
        "script_location", str(project_root / "backend" / "digitalme" / "db" / "migrations")
    )
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    return config


@contextmanager
def _archive_queries() -> Iterator[ArchiveQueryService]:
    engine = create_engine()
    try:
        yield ArchiveQueryService(create_session_factory(engine))
    finally:
        engine.dispose()


@contextmanager
def _episode_service() -> Iterator[EpisodeService]:
    engine = create_engine()
    try:
        yield EpisodeService(create_session_factory(engine))
    finally:
        engine.dispose()


@contextmanager
def _memory_service() -> Iterator[MemoryService]:
    settings = get_settings()
    engine = create_engine(settings)
    provider = DeepSeekJsonProvider(settings) if settings.deepseek_configured else None
    try:
        yield MemoryService(create_session_factory(engine), provider)
    finally:
        engine.dispose()


@contextmanager
def _retrieval_service() -> Iterator[RetrievalService]:
    settings = get_settings()
    engine = create_engine(settings)
    provider = DeepSeekJsonProvider(settings) if settings.deepseek_configured else None
    try:
        yield RetrievalService(create_session_factory(engine), provider)
    finally:
        engine.dispose()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show the installed version."),
) -> None:
    """Run DigitalMe commands."""

    if version:
        typer.echo(__version__)
        raise typer.Exit
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Upgrade the local database schema."""

    settings = get_settings()
    settings.ensure_local_directories()
    command.upgrade(_alembic_config(), revision)


@db_app.command("downgrade")
def db_downgrade(revision: str = "-1") -> None:
    """Downgrade the local database schema."""

    command.downgrade(_alembic_config(), revision)


@ingest_app.command("chatgpt")
def ingest_chatgpt(
    archive: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Official ChatGPT data export ZIP.",
        ),
    ],
) -> None:
    """Import a ChatGPT export into the local historical archive."""

    settings = get_settings()
    engine = create_engine(settings)
    try:
        importer = ChatGPTImporter(
            create_session_factory(engine),
            ArtifactStore(settings.raw_store_path),
        )
        result = importer.import_zip(archive)
    finally:
        engine.dispose()
    typer.echo(
        f"job={result.job_id} sessions_created={result.sessions_created} "
        f"sessions_updated={result.sessions_updated} messages_created={result.messages_created} "
        f"messages_updated={result.messages_updated} warnings={result.warnings}"
        f" redactions={result.redactions}"
    )


@ingest_app.command("codex")
def ingest_codex(
    codex_home: Annotated[
        Path | None,
        typer.Option(help="Codex home containing sessions/ and archived_sessions/."),
    ] = None,
) -> None:
    """Scan local Codex rollout history once; continuous watching is intentionally deferred."""

    settings = get_settings()
    home = (codex_home or settings.codex_home).expanduser().resolve()
    engine = create_engine(settings)
    try:
        result = CodexImporter(
            create_session_factory(engine),
            ArtifactStore(settings.raw_store_path),
        ).scan(home)
    finally:
        engine.dispose()
    typer.echo(
        f"job={result.job_id} files_scanned={result.files_scanned} "
        f"sessions_created={result.sessions_created} sessions_updated={result.sessions_updated} "
        f"messages_created={result.messages_created} messages_updated={result.messages_updated} "
        f"warnings={result.warnings} redactions={result.redactions}"
    )


@sessions_app.command("list")
def sessions_list(
    limit: int = typer.Option(20, min=1, max=500, help="Maximum sessions to display."),
    offset: int = typer.Option(0, min=0, help="Number of sessions to skip."),
    source_type: str | None = typer.Option(None, help="Filter by source type."),
) -> None:
    """List recently updated canonical sessions without loading message bodies."""

    with _archive_queries() as service:
        page = service.list_sessions(
            limit=limit,
            offset=offset,
            source_type=source_type,
        )
    if not page.items:
        typer.echo("No sessions found.")
        return
    for item in page.items:
        typer.echo(
            f"{item.id}\t{item.source_type}\t{item.source_updated_at or '-'}\t"
            f"{item.message_count}\t{item.title or '(untitled)'}"
        )
    typer.echo(f"Showing {len(page.items)} of {page.total} sessions (offset={page.offset}).")


@sessions_app.command("show")
def sessions_show(session_id: str) -> None:
    """Show one canonical session using only its redacted message view."""

    with _archive_queries() as service:
        detail = service.get_session(session_id)
    if detail is None:
        typer.echo("Session not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(_json(asdict(detail)))


@jobs_app.command("list")
def jobs_list(
    limit: int = typer.Option(20, min=1, max=500, help="Maximum jobs to display."),
    offset: int = typer.Option(0, min=0, help="Number of jobs to skip."),
    status: str | None = typer.Option(None, help="Filter by job status."),
    kind: str | None = typer.Option(None, help="Filter by job kind."),
) -> None:
    """List recent ingestion jobs and their safe status summaries."""

    with _archive_queries() as service:
        page = service.list_jobs(limit=limit, offset=offset, status=status, kind=kind)
    if not page.items:
        typer.echo("No ingestion jobs found.")
        return
    for item in page.items:
        typer.echo(
            f"{item.id}\t{item.source_type or '-'}\t{item.status}\t{item.stage or '-'}\t{item.kind}"
        )
    typer.echo(f"Showing {len(page.items)} of {page.total} jobs (offset={page.offset}).")


@jobs_app.command("inspect")
def jobs_inspect(job_id: str) -> None:
    """Inspect one ingestion job without exposing imported message bodies."""

    with _archive_queries() as service:
        detail = service.get_job(job_id)
    if detail is None:
        typer.echo("Ingestion job not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(_json(asdict(detail)))


@episodes_app.command("rebuild")
def episodes_rebuild(
    session_id: str | None = typer.Option(None, help="Rebuild only this Session ID."),
) -> None:
    """Deterministically rebuild Episode segments from safe message views."""

    try:
        with _episode_service() as service:
            result = (
                service.rebuild_session(session_id)
                if session_id is not None
                else service.rebuild_all()
            )
    except (LookupError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(_json(asdict(result)))


@episodes_app.command("list")
def episodes_list(
    limit: int = typer.Option(20, min=1, max=500),
    offset: int = typer.Option(0, min=0),
    session_id: str | None = typer.Option(None, help="Filter by Session ID."),
    source_type: str | None = typer.Option(None, help="Filter by source type."),
) -> None:
    """List deterministic Episode segments."""

    with _episode_service() as service:
        page = service.list_episodes(
            limit=limit,
            offset=offset,
            session_id=session_id,
            source_type=source_type,
        )
    if not page.items:
        typer.echo("No episodes found.")
        return
    for item in page.items:
        typer.echo(
            f"{item.id}\t{item.source_type}\t{item.start_at or '-'}\t"
            f"{item.message_count}\t{item.title}"
        )
    typer.echo(f"Showing {len(page.items)} of {page.total} episodes (offset={page.offset}).")


@episodes_app.command("show")
def episodes_show(episode_id: str) -> None:
    """Show one Episode and its redacted source-message evidence."""

    with _episode_service() as service:
        detail = service.get_episode(episode_id)
    if detail is None:
        typer.echo("Episode not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(_json(asdict(detail)))


@memories_app.command("extract")
def memories_extract(episode_id: str) -> None:
    """Extract semantic Episode fields and evidence-linked Memory Candidates."""

    try:
        with _memory_service() as service:
            result = service.extract_episode(episode_id)
    except ProviderConfigurationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except (
        ExtractionValidationError,
        LookupError,
        ProviderPolicyError,
        ProviderResponseError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(_json(asdict(result)))


@memories_app.command("list")
def memories_list(
    limit: int = typer.Option(20, min=1, max=500),
    offset: int = typer.Option(0, min=0),
    status: str | None = typer.Option(None),
    candidate_type: str | None = typer.Option(None, "--type"),
) -> None:
    """List extracted Memory Candidates."""

    with _memory_service() as service:
        page = service.list_candidates(
            limit=limit,
            offset=offset,
            status=status,
            candidate_type=candidate_type,
        )
    if not page.items:
        typer.echo("No memory candidates found.")
        return
    for item in page.items:
        typer.echo(
            f"{item.id}\t{item.status}\t{item.candidate_type}\t"
            f"{item.evidence_strength}\t{item.content}"
        )
    typer.echo(f"Showing {len(page.items)} of {page.total} memories (offset={page.offset}).")


@memories_app.command("show")
def memories_show(candidate_id: str) -> None:
    """Show a Memory Candidate and its redacted Evidence."""

    with _memory_service() as service:
        detail = service.get_candidate(candidate_id)
    if detail is None:
        typer.echo("Memory Candidate not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(_json(asdict(detail)))


@memories_app.command("confirm")
def memories_confirm(candidate_id: str) -> None:
    """Confirm an evidence-linked Memory Candidate."""

    with _memory_service() as service:
        detail = service.set_candidate_status(candidate_id, "confirmed")
    typer.echo(_json(asdict(detail)))


@memories_app.command("reject")
def memories_reject(candidate_id: str) -> None:
    """Reject a Memory Candidate without deleting its evidence."""

    with _memory_service() as service:
        detail = service.set_candidate_status(candidate_id, "rejected")
    typer.echo(_json(asdict(detail)))


@app.command("retrieve")
def retrieve_memories(
    query: str = typer.Argument(..., help="Question or keywords to search confirmed memories."),
    limit: int = typer.Option(10, min=1, max=20),
) -> None:
    """Search only user-confirmed memories using deterministic local ranking."""

    try:
        with _retrieval_service() as service:
            result = service.retrieve(query, limit=limit)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if not result.hits:
        typer.echo("No relevant confirmed memories found.")
        return
    for hit in result.hits:
        typer.echo(f"{hit.candidate_id}\t{hit.score:.4f}\t{hit.evidence_strength}\t{hit.content}")
    typer.echo(
        f"Showing {len(result.hits)} matches from {result.confirmed_scanned} confirmed memories."
    )


@app.command("ask")
def ask_memories(
    query: str = typer.Argument(..., help="Personal question answered from confirmed memories."),
    limit: int = typer.Option(8, min=1, max=20),
) -> None:
    """Explicitly ask the configured provider over a bounded confirmed Memory Pack."""

    try:
        with _retrieval_service() as service:
            result = service.ask(query, limit=limit)
    except ProviderConfigurationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except (
        NoRelevantMemoriesError,
        ProviderPolicyError,
        ProviderResponseError,
        RetrievalValidationError,
        ValueError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(_json(asdict(result)))
