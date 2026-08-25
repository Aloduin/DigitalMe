from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


def test_initial_migration_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "digitalme.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")
    tables = set(inspect_database(database_path))
    assert {
        "alembic_version",
        "artifacts",
        "ingestion_errors",
        "ingestion_jobs",
        "messages",
        "sessions",
        "sources",
    } <= tables
    assert {
        "redacted_text",
        "redaction_spans",
        "sensitivity",
    } <= set(inspect_columns(database_path, "messages"))

    command.downgrade(config, "base")
    assert inspect_database(database_path) == ["alembic_version"]

    command.upgrade(config, "head")
    assert "sessions" in inspect_database(database_path)


def inspect_database(database_path: Path) -> list[str]:
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        return inspect(engine).get_table_names()
    finally:
        engine.dispose()


def inspect_columns(database_path: Path, table_name: str) -> list[str]:
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        return [str(column["name"]) for column in inspect(engine).get_columns(table_name)]
    finally:
        engine.dispose()
