"""DigitalMe command-line interface."""

from pathlib import Path
from typing import Annotated

import typer
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from digitalme import __version__
from digitalme.config import get_settings
from digitalme.db.session import create_engine, create_session_factory
from digitalme.ingestion.chatgpt import ChatGPTImporter
from digitalme.ingestion.common import ArtifactStore
from digitalme.models import Message, SessionRecord

app = typer.Typer(help="DigitalMe Memory Engine")
db_app = typer.Typer(help="Manage the local database")
ingest_app = typer.Typer(help="Import historical source data")
sessions_app = typer.Typer(help="Browse canonical sessions")
app.add_typer(db_app, name="db")
app.add_typer(ingest_app, name="ingest")
app.add_typer(sessions_app, name="sessions")


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(project_root / "alembic.ini")
    config.set_main_option(
        "script_location", str(project_root / "backend" / "digitalme" / "db" / "migrations")
    )
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    return config


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
    )


@sessions_app.command("list")
def sessions_list(
    limit: int = typer.Option(20, min=1, max=500, help="Maximum sessions to display."),
) -> None:
    """List recently updated canonical sessions without loading message bodies."""

    engine = create_engine()
    factory = create_session_factory(engine)
    try:
        with factory() as db:
            rows = db.execute(
                select(
                    SessionRecord.id,
                    SessionRecord.title,
                    SessionRecord.source_updated_at,
                    func.count(Message.id).label("message_count"),
                )
                .outerjoin(Message)
                .group_by(SessionRecord.id)
                .order_by(SessionRecord.source_updated_at.desc())
                .limit(limit)
            ).all()
    finally:
        engine.dispose()
    if not rows:
        typer.echo("No sessions found.")
        return
    for session_id, title, updated_at, message_count in rows:
        typer.echo(f"{session_id}\t{updated_at or '-'}\t{message_count}\t{title or '(untitled)'}")
