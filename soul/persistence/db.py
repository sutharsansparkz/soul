"""SQLite-only database helpers for the refactored runtime."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine

from soul.bootstrap.errors import ConfigurationError


_ENGINE_CACHE: dict[str, Engine] = {}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_sqlite_url(database_url: str) -> str:
    if not database_url or not database_url.startswith("sqlite:///"):
        raise ConfigurationError(
            "This runtime is SQLite-only. Set DATABASE_URL to a sqlite:/// path."
        )
    return database_url


def normalize_database_url(database: str | Path) -> str:
    if isinstance(database, Path):
        return f"sqlite:///{database.resolve().as_posix()}"
    return ensure_sqlite_url(database)


def _ensure_parent(database_url: str) -> None:
    raw_path = database_url.removeprefix("sqlite:///")
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)


def get_engine(database: str | Path) -> Engine:
    database_url = normalize_database_url(database)
    if database_url not in _ENGINE_CACHE:
        _ensure_parent(database_url)
        engine = create_engine(
            database_url,
            future=True,
            connect_args={"timeout": 15},
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

        _ENGINE_CACHE[database_url] = engine
    return _ENGINE_CACHE[database_url]


@contextmanager
def connect(database: str | Path) -> Iterator[Connection]:
    connection = get_engine(database).connect()
    try:
        yield connection
    finally:
        connection.close()
