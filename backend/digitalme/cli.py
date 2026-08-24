"""DigitalMe command-line interface."""

from pathlib import Path

import typer
from alembic import command
from alembic.config import Config

from digitalme import __version__
from digitalme.config import get_settings

app = typer.Typer(help="DigitalMe Memory Engine")
db_app = typer.Typer(help="Manage the local database")
app.add_typer(db_app, name="db")


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
