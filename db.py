from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_database(database: Path | str) -> str:
    if isinstance(database, Path):
        return f"sqlite:///{database.resolve().as_posix()}"
    return database


def _ensure_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    raw_path = database_url.removeprefix("sqlite:///")
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)


def _engine_key(database: Path | str) -> str:
    return _normalize_database(database)


_ENGINE_CACHE: dict[str, Engine] = {}


def _get_engine(database: Path | str) -> Engine:
    database_url = _engine_key(database)
    if database_url not in _ENGINE_CACHE:
        _ensure_parent(database_url)
        _ENGINE_CACHE[database_url] = create_engine(database_url, future=True)
    return _ENGINE_CACHE[database_url]


@contextmanager
def connect(database: Path | str) -> Iterator[Connection]:
    connection = _get_engine(database).connect()
    try:
        yield connection
    finally:
        connection.close()


def init_db(database: Path | str) -> None:
    database_url = _normalize_database(database)
    engine = _get_engine(database_url)
    statements = [
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            companion_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            user_mood TEXT,
            companion_state TEXT,
            provider TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}',
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            label TEXT NOT NULL,
            content TEXT NOT NULL,
            importance REAL DEFAULT 0.5,
            source TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS milestones (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            note TEXT NOT NULL,
            session_id TEXT,
            occurred_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS drift_log (
            id TEXT PRIMARY KEY,
            run_date TEXT NOT NULL,
            dimensions_before TEXT NOT NULL,
            dimensions_after TEXT NOT NULL,
            resonance_signals TEXT NOT NULL,
            notes TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS consolidated_sessions (
            session_id TEXT PRIMARY KEY,
            consolidated_at TEXT NOT NULL,
            source TEXT DEFAULT 'nightly'
        )
        """,
    ]
    with engine.begin() as connection:
        if database_url.startswith("sqlite:///"):
            connection.exec_driver_sql("PRAGMA journal_mode = WAL;")
        for statement in statements:
            connection.exec_driver_sql(statement)


def create_session(database: Path | str, companion_name: str, session_id: str | None = None) -> str:
    session_id = session_id or str(uuid.uuid4())
    with _get_engine(database).begin() as connection:
        connection.execute(
            text("INSERT INTO sessions (id, companion_name, started_at) VALUES (:id, :companion_name, :started_at)"),
            {"id": session_id, "companion_name": companion_name, "started_at": utcnow_iso()},
        )
    return session_id


def session_exists(database: Path | str, session_id: str) -> bool:
    with connect(database) as connection:
        row = connection.execute(
            text("SELECT 1 FROM sessions WHERE id = :session_id LIMIT 1"),
            {"session_id": session_id},
        ).first()
    return row is not None


def close_session(database: Path | str, session_id: str) -> None:
    with _get_engine(database).begin() as connection:
        connection.execute(
            text("UPDATE sessions SET ended_at = :ended_at WHERE id = :session_id"),
            {"ended_at": utcnow_iso(), "session_id": session_id},
        )


def log_message(
    database: Path | str,
    *,
    session_id: str,
    role: str,
    content: str,
    user_mood: str | None = None,
    companion_state: str | None = None,
    provider: str | None = None,
    metadata: dict[str, object] | None = None,
) -> str:
    message_id = str(uuid.uuid4())
    with _get_engine(database).begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO messages (
                    id, session_id, role, content, user_mood, companion_state, provider, created_at, metadata_json
                ) VALUES (
                    :id, :session_id, :role, :content, :user_mood, :companion_state, :provider, :created_at, :metadata_json
                )
                """
            ),
            {
                "id": message_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "user_mood": user_mood,
                "companion_state": companion_state,
                "provider": provider,
                "created_at": utcnow_iso(),
                "metadata_json": json.dumps(metadata or {}, ensure_ascii=True),
            },
        )
    return message_id


def _fetch_dicts(connection: Connection, statement: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
    rows = connection.execute(text(statement), params or {}).mappings().all()
    return [dict(row) for row in rows]


def get_session_messages(database: Path | str, session_id: str) -> list[dict[str, object]]:
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            """
            SELECT role, content, user_mood, companion_state, provider, created_at, metadata_json
            FROM messages
            WHERE session_id = :session_id
            ORDER BY created_at ASC
            """,
            {"session_id": session_id},
        )


def get_recent_session_messages(database: Path | str, session_id: str, limit: int = 12) -> list[dict[str, object]]:
    with connect(database) as connection:
        rows = _fetch_dicts(
            connection,
            """
            SELECT role, content, user_mood, companion_state, provider, created_at, metadata_json
            FROM messages
            WHERE session_id = :session_id
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"session_id": session_id, "limit": limit},
        )
    return list(reversed(rows))


def get_last_completed_session_id(database: Path | str, current_session_id: str | None = None) -> str | None:
    with connect(database) as connection:
        row = connection.execute(
            text(
                """
                SELECT id
                FROM sessions
                WHERE ended_at IS NOT NULL
                  AND (:current_session_id IS NULL OR id != :current_session_id)
                ORDER BY started_at DESC
                LIMIT 1
                """
            ),
            {"current_session_id": current_session_id},
        ).mappings().first()
    return str(row["id"]) if row else None


def save_memory(
    database: Path | str,
    *,
    label: str,
    content: str,
    session_id: str | None = None,
    importance: float = 0.5,
    source: str = "manual",
) -> str:
    memory_id = str(uuid.uuid4())
    with _get_engine(database).begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO memories (id, session_id, label, content, importance, source, created_at)
                VALUES (:id, :session_id, :label, :content, :importance, :source, :created_at)
                """
            ),
            {
                "id": memory_id,
                "session_id": session_id,
                "label": label,
                "content": content,
                "importance": importance,
                "source": source,
                "created_at": utcnow_iso(),
            },
        )
    return memory_id


def list_memories(database: Path | str, limit: int = 20) -> list[dict[str, object]]:
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            """
            SELECT id, session_id, label, content, importance, source, created_at
            FROM memories
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )


def search_memories(database: Path | str, query: str, limit: int = 10) -> list[dict[str, object]]:
    pattern = f"%{query.lower()}%"
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            """
            SELECT id, session_id, label, content, importance, source, created_at
            FROM memories
            WHERE lower(label) LIKE :pattern OR lower(content) LIKE :pattern
            ORDER BY importance DESC, created_at DESC
            LIMIT :limit
            """,
            {"pattern": pattern, "limit": limit},
        )


def clear_memories(database: Path | str) -> int:
    with _get_engine(database).begin() as connection:
        result = connection.execute(text("DELETE FROM memories"))
    return int(result.rowcount or 0)


def insert_milestone(database: Path | str, *, kind: str, note: str, session_id: str | None = None) -> str:
    milestone_id = str(uuid.uuid4())
    with _get_engine(database).begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO milestones (id, kind, note, session_id, occurred_at)
                VALUES (:id, :kind, :note, :session_id, :occurred_at)
                """
            ),
            {
                "id": milestone_id,
                "kind": kind,
                "note": note,
                "session_id": session_id,
                "occurred_at": utcnow_iso(),
            },
        )
    return milestone_id


def milestone_exists(database: Path | str, kind: str) -> bool:
    with connect(database) as connection:
        row = connection.execute(
            text("SELECT 1 FROM milestones WHERE kind = :kind LIMIT 1"),
            {"kind": kind},
        ).first()
    return row is not None


def list_milestones(database: Path | str, limit: int = 50) -> list[dict[str, object]]:
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            """
            SELECT id, kind, note, session_id, occurred_at
            FROM milestones
            ORDER BY occurred_at DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )


def count_messages(database: Path | str, role: str | None = None) -> int:
    with connect(database) as connection:
        if role:
            row = connection.execute(
                text("SELECT COUNT(*) AS count FROM messages WHERE role = :role"),
                {"role": role},
            ).mappings().first()
        else:
            row = connection.execute(text("SELECT COUNT(*) AS count FROM messages")).mappings().first()
    return int(row["count"])


def count_sessions(database: Path | str) -> int:
    with connect(database) as connection:
        row = connection.execute(text("SELECT COUNT(*) AS count FROM sessions")).mappings().first()
    return int(row["count"])


def get_last_message_timestamp(database: Path | str) -> str | None:
    with connect(database) as connection:
        row = connection.execute(
            text("SELECT created_at FROM messages ORDER BY created_at DESC LIMIT 1")
        ).mappings().first()
    return str(row["created_at"]) if row else None


def list_drift_log(database: Path | str, limit: int = 20) -> list[dict[str, object]]:
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            """
            SELECT id, run_date, dimensions_before, dimensions_after, resonance_signals, notes
            FROM drift_log
            ORDER BY run_date DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )


def list_sessions(
    database: Path | str,
    *,
    completed_only: bool = False,
    limit: int | None = None,
) -> list[dict[str, object]]:
    where = "WHERE ended_at IS NOT NULL" if completed_only else ""
    limit_sql = "LIMIT :limit" if limit is not None else ""
    params: dict[str, object] = {"limit": limit} if limit is not None else {}
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            f"""
            SELECT id, companion_name, started_at, ended_at
            FROM sessions
            {where}
            ORDER BY started_at ASC
            {limit_sql}
            """,
            params,
        )


def list_unconsolidated_completed_session_ids(database: Path | str) -> list[str]:
    with connect(database) as connection:
        rows = _fetch_dicts(
            connection,
            """
            SELECT s.id
            FROM sessions s
            LEFT JOIN consolidated_sessions c ON c.session_id = s.id
            WHERE s.ended_at IS NOT NULL
              AND c.session_id IS NULL
            ORDER BY s.started_at ASC
            """,
        )
    return [str(row["id"]) for row in rows]


def mark_session_consolidated(database: Path | str, session_id: str, source: str = "nightly") -> None:
    with _get_engine(database).begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO consolidated_sessions (session_id, consolidated_at, source)
                VALUES (:session_id, :consolidated_at, :source)
                ON CONFLICT(session_id) DO UPDATE SET
                    consolidated_at = excluded.consolidated_at,
                    source = excluded.source
                """
            ),
            {"session_id": session_id, "consolidated_at": utcnow_iso(), "source": source},
        )


def is_session_consolidated(database: Path | str, session_id: str) -> bool:
    with connect(database) as connection:
        row = connection.execute(
            text("SELECT 1 FROM consolidated_sessions WHERE session_id = :session_id LIMIT 1"),
            {"session_id": session_id},
        ).first()
    return row is not None
