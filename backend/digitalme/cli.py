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

app = typer.Typer(help="DigitalMe Memory Engine")
db_app = typer.Typer(help="Manage the local database")
ingest_app = typer.Typer(help="Import historical source data")
sessions_app = typer.Typer(help="Browse canonical sessions")
jobs_app = typer.Typer(help="Inspect ingestion jobs")
episodes_app = typer.Typer(help="Build and browse episodic memory")
app.add_typer(db_app, name="db")
app.add_typer(ingest_app, name="ingest")
app.add_typer(sessions_app, name="sessions")
app.add_typer(jobs_app, name="jobs")
app.add_typer(episodes_app, name="episodes")


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

    with _episode_service() as service:
        result = (
            service.rebuild_session(session_id) if session_id is not None else service.rebuild_all()
        )
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
