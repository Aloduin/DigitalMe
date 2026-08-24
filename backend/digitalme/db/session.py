"""SQLite engine and session factory construction."""

from collections.abc import Iterator

from sqlalchemy import Engine, event
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.orm import Session, sessionmaker

from digitalme.config import Settings, get_settings


def _configure_sqlite(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def create_engine(settings: Settings | None = None) -> Engine:
    """Create an engine with safe SQLite defaults."""

    resolved_settings = settings or get_settings()
    resolved_settings.ensure_local_directories()
    engine = sqlalchemy_create_engine(resolved_settings.database_url, pool_pre_ping=True)
    if resolved_settings.database_url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the shared unit-of-work factory."""

    return sessionmaker(bind=engine, expire_on_commit=False)


_engine = create_engine()
SessionLocal = create_session_factory(_engine)


def get_db_session() -> Iterator[Session]:
    """FastAPI dependency yielding a transaction-scoped session."""

    with SessionLocal() as session:
        yield session
