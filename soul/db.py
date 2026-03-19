from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
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
        """
        CREATE TABLE IF NOT EXISTS session_memory_exports (
            session_id TEXT PRIMARY KEY,
            exported_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS episodic_memory (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            emotional_tag TEXT,
            memory_type TEXT DEFAULT 'moment',
            word_count INTEGER DEFAULT 0,
            flagged INTEGER DEFAULT 0,
            ref_count INTEGER DEFAULT 0,
            tier TEXT DEFAULT 'present'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS memory_scores (
            memory_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            score_emotional REAL NOT NULL DEFAULT 0.5,
            score_retrieval REAL NOT NULL DEFAULT 0.0,
            score_temporal REAL NOT NULL DEFAULT 1.0,
            score_flagged REAL NOT NULL DEFAULT 0.0,
            score_volume REAL NOT NULL DEFAULT 0.3,
            hms_score REAL NOT NULL DEFAULT 0.5,
            last_computed TEXT NOT NULL,
            last_retrieved TEXT,
            decay_rate REAL DEFAULT 0.023,
            FOREIGN KEY(memory_id) REFERENCES episodic_memory(id)
        )
        """,
    ]
    with engine.begin() as connection:
        if database_url.startswith("sqlite:///"):
            connection.exec_driver_sql("PRAGMA journal_mode = WAL;")
        for statement in statements:
            connection.exec_driver_sql(statement)
        _migrate_hms_schema(connection)
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_memory_scores_user_score ON memory_scores(user_id, hms_score DESC)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_episodic_memory_user_tier ON episodic_memory(user_id, tier, timestamp DESC)"
        )


def _migrate_hms_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "episodic_memory" in tables:
        _ensure_columns(
            connection,
            inspector=inspector,
            table_name="episodic_memory",
            columns={
                "word_count": "INTEGER DEFAULT 0",
                "flagged": "INTEGER DEFAULT 0",
                "ref_count": "INTEGER DEFAULT 0",
                "tier": "TEXT DEFAULT 'present'",
                "memory_type": "TEXT DEFAULT 'moment'",
            },
        )
        connection.execute(
            text(
                """
                UPDATE episodic_memory
                SET word_count = COALESCE(word_count, 0),
                    flagged = COALESCE(flagged, 0),
                    ref_count = COALESCE(ref_count, 0),
                    tier = COALESCE(NULLIF(tier, ''), 'present'),
                    memory_type = COALESCE(NULLIF(memory_type, ''), 'moment')
                """
            )
        )

    if "memory_scores" in tables:
        _ensure_columns(
            connection,
            inspector=inspector,
            table_name="memory_scores",
            columns={
                "score_emotional": "REAL NOT NULL DEFAULT 0.5",
                "score_retrieval": "REAL NOT NULL DEFAULT 0.0",
                "score_temporal": "REAL NOT NULL DEFAULT 1.0",
                "score_flagged": "REAL NOT NULL DEFAULT 0.0",
                "score_volume": "REAL NOT NULL DEFAULT 0.3",
                "hms_score": "REAL NOT NULL DEFAULT 0.5",
                "last_computed": "TEXT",
                "last_retrieved": "TEXT",
                "decay_rate": "REAL DEFAULT 0.023",
            },
        )
        connection.execute(
            text(
                """
                UPDATE memory_scores
                SET score_emotional = COALESCE(score_emotional, 0.5),
                    score_retrieval = COALESCE(score_retrieval, 0.0),
                    score_temporal = COALESCE(score_temporal, 1.0),
                    score_flagged = COALESCE(score_flagged, 0.0),
                    score_volume = COALESCE(score_volume, 0.3),
                    hms_score = COALESCE(hms_score, 0.5),
                    decay_rate = COALESCE(decay_rate, 0.023),
                    last_computed = COALESCE(NULLIF(last_computed, ''), :now_iso)
                """
            ),
            {"now_iso": utcnow_iso()},
        )


def _ensure_columns(
    connection: Connection,
    *,
    inspector,
    table_name: str,
    columns: dict[str, str],
) -> None:
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name, definition in columns.items():
        if column_name in existing:
            continue
        connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


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


def create_episodic_memory(
    database: Path | str,
    *,
    user_id: str,
    session_id: str,
    content: str,
    timestamp: str | None = None,
    emotional_tag: str | None = None,
    memory_type: str = "moment",
    word_count: int | None = None,
    flagged: bool = False,
    ref_count: int = 0,
    tier: str = "present",
    memory_id: str | None = None,
) -> str:
    episodic_id = memory_id or str(uuid.uuid4())
    with _get_engine(database).begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO episodic_memory (
                    id, user_id, session_id, timestamp, content, emotional_tag,
                    memory_type, word_count, flagged, ref_count, tier
                )
                VALUES (
                    :id, :user_id, :session_id, :timestamp, :content, :emotional_tag,
                    :memory_type, :word_count, :flagged, :ref_count, :tier
                )
                """
            ),
            {
                "id": episodic_id,
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": timestamp or utcnow_iso(),
                "content": content,
                "emotional_tag": emotional_tag,
                "memory_type": memory_type,
                "word_count": int(word_count if word_count is not None else len(content.split())),
                "flagged": 1 if flagged else 0,
                "ref_count": int(ref_count),
                "tier": tier,
            },
        )
    return episodic_id


def get_episodic_memory(database: Path | str, memory_id: str) -> dict[str, object] | None:
    with connect(database) as connection:
        row = connection.execute(
            text(
                """
                SELECT id, user_id, session_id, timestamp, content, emotional_tag, memory_type,
                       word_count, flagged, ref_count, tier
                FROM episodic_memory
                WHERE id = :memory_id
                LIMIT 1
                """
            ),
            {"memory_id": memory_id},
        ).mappings().first()
    return dict(row) if row else None


def list_episodic_memories(
    database: Path | str,
    *,
    user_id: str | None = None,
    include_cold: bool = True,
    limit: int = 50,
) -> list[dict[str, object]]:
    predicates: list[str] = []
    params: dict[str, object] = {"limit": limit}
    if user_id is not None:
        predicates.append("user_id = :user_id")
        params["user_id"] = user_id
    if not include_cold:
        predicates.append("tier != 'cold'")
    where_sql = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            f"""
            SELECT id, user_id, session_id, timestamp, content, emotional_tag, memory_type,
                   word_count, flagged, ref_count, tier
            FROM episodic_memory
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT :limit
            """,
            params,
        )


def search_episodic_memories(
    database: Path | str,
    query: str,
    *,
    user_id: str | None = None,
    include_cold: bool = True,
    limit: int = 20,
) -> list[dict[str, object]]:
    predicates = ["lower(content) LIKE :pattern"]
    params: dict[str, object] = {"pattern": f"%{query.casefold()}%", "limit": limit}
    if user_id is not None:
        predicates.append("em.user_id = :user_id")
        params["user_id"] = user_id
    if not include_cold:
        predicates.append("em.tier != 'cold'")
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            f"""
            SELECT em.id, em.user_id, em.session_id, em.timestamp, em.content, em.emotional_tag, em.memory_type,
                   em.word_count, em.flagged, em.ref_count, em.tier, COALESCE(ms.hms_score, 0.5) AS hms_score
            FROM episodic_memory em
            LEFT JOIN memory_scores ms ON ms.memory_id = em.id
            WHERE {' AND '.join(predicates)}
            ORDER BY hms_score DESC, em.timestamp DESC
            LIMIT :limit
            """,
            params,
        )


def list_top_episodic_memories(
    database: Path | str,
    *,
    user_id: str | None = None,
    include_cold: bool = True,
    limit: int = 10,
) -> list[dict[str, object]]:
    predicates: list[str] = []
    params: dict[str, object] = {"limit": limit}
    if user_id is not None:
        predicates.append("em.user_id = :user_id")
        params["user_id"] = user_id
    if not include_cold:
        predicates.append("em.tier != 'cold'")
    where_sql = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            f"""
            SELECT em.id, em.user_id, em.session_id, em.timestamp, em.content, em.emotional_tag, em.memory_type,
                   em.word_count, em.flagged, em.ref_count, em.tier,
                   COALESCE(ms.score_emotional, 0.5) AS score_emotional,
                   COALESCE(ms.score_retrieval, 0.0) AS score_retrieval,
                   COALESCE(ms.score_temporal, 1.0) AS score_temporal,
                   COALESCE(ms.score_flagged, 0.0) AS score_flagged,
                   COALESCE(ms.score_volume, 0.3) AS score_volume,
                   COALESCE(ms.hms_score, 0.5) AS hms_score,
                   ms.last_computed,
                   ms.last_retrieved
            FROM episodic_memory em
            LEFT JOIN memory_scores ms ON ms.memory_id = em.id
            {where_sql}
            ORDER BY hms_score DESC, em.timestamp DESC
            LIMIT :limit
            """,
            params,
        )


def list_cold_memories(
    database: Path | str,
    *,
    user_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    predicates = ["em.tier = 'cold'"]
    params: dict[str, object] = {"limit": limit}
    if user_id is not None:
        predicates.append("em.user_id = :user_id")
        params["user_id"] = user_id
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            f"""
            SELECT em.id, em.user_id, em.session_id, em.timestamp, em.content, em.emotional_tag, em.memory_type,
                   em.word_count, em.flagged, em.ref_count, em.tier, COALESCE(ms.hms_score, 0.5) AS hms_score
            FROM episodic_memory em
            LEFT JOIN memory_scores ms ON ms.memory_id = em.id
            WHERE {' AND '.join(predicates)}
            ORDER BY em.timestamp DESC
            LIMIT :limit
            """,
            params,
        )


def update_episodic_memory_fields(
    database: Path | str,
    memory_id: str,
    *,
    ref_count_delta: int = 0,
    flagged: bool | None = None,
    tier: str | None = None,
) -> None:
    updates: list[str] = []
    params: dict[str, object] = {"memory_id": memory_id}
    if ref_count_delta:
        updates.append("ref_count = ref_count + :ref_count_delta")
        params["ref_count_delta"] = ref_count_delta
    if flagged is not None:
        updates.append("flagged = :flagged")
        params["flagged"] = 1 if flagged else 0
    if tier is not None:
        updates.append("tier = :tier")
        params["tier"] = tier
    if not updates:
        return
    with _get_engine(database).begin() as connection:
        connection.execute(
            text(
                f"""
                UPDATE episodic_memory
                SET {", ".join(updates)}
                WHERE id = :memory_id
                """
            ),
            params,
        )


def upsert_memory_score(
    database: Path | str,
    *,
    memory_id: str,
    user_id: str,
    score_emotional: float,
    score_retrieval: float,
    score_temporal: float,
    score_flagged: float,
    score_volume: float,
    hms_score: float,
    last_computed: str | None = None,
    last_retrieved: str | None = None,
    decay_rate: float = 0.023,
) -> None:
    with _get_engine(database).begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO memory_scores (
                    memory_id, user_id, score_emotional, score_retrieval, score_temporal,
                    score_flagged, score_volume, hms_score, last_computed, last_retrieved, decay_rate
                )
                VALUES (
                    :memory_id, :user_id, :score_emotional, :score_retrieval, :score_temporal,
                    :score_flagged, :score_volume, :hms_score, :last_computed, :last_retrieved, :decay_rate
                )
                ON CONFLICT(memory_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    score_emotional = excluded.score_emotional,
                    score_retrieval = excluded.score_retrieval,
                    score_temporal = excluded.score_temporal,
                    score_flagged = excluded.score_flagged,
                    score_volume = excluded.score_volume,
                    hms_score = excluded.hms_score,
                    last_computed = excluded.last_computed,
                    last_retrieved = excluded.last_retrieved,
                    decay_rate = excluded.decay_rate
                """
            ),
            {
                "memory_id": memory_id,
                "user_id": user_id,
                "score_emotional": score_emotional,
                "score_retrieval": score_retrieval,
                "score_temporal": score_temporal,
                "score_flagged": score_flagged,
                "score_volume": score_volume,
                "hms_score": hms_score,
                "last_computed": last_computed or utcnow_iso(),
                "last_retrieved": last_retrieved,
                "decay_rate": decay_rate,
            },
        )


def get_memory_score(database: Path | str, memory_id: str) -> dict[str, object] | None:
    with connect(database) as connection:
        row = connection.execute(
            text(
                """
                SELECT memory_id, user_id, score_emotional, score_retrieval, score_temporal,
                       score_flagged, score_volume, hms_score, last_computed, last_retrieved, decay_rate
                FROM memory_scores
                WHERE memory_id = :memory_id
                LIMIT 1
                """
            ),
            {"memory_id": memory_id},
        ).mappings().first()
    return dict(row) if row else None


def list_memory_scores_for_decay(database: Path | str, *, user_id: str | None = None) -> list[dict[str, object]]:
    params: dict[str, object] = {}
    where_sql = ""
    if user_id is not None:
        # Filter by episodic owner so legacy rows without score records are still decayed/backfilled.
        where_sql = "WHERE em.user_id = :user_id"
        params["user_id"] = user_id
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            f"""
            SELECT em.id, em.user_id, em.session_id, em.timestamp, em.content, em.emotional_tag, em.memory_type,
                   em.word_count, em.flagged, em.ref_count, em.tier,
                   COALESCE(ms.score_emotional, 0.5) AS score_emotional,
                   COALESCE(ms.score_retrieval, 0.0) AS score_retrieval,
                   COALESCE(ms.score_temporal, 1.0) AS score_temporal,
                   COALESCE(ms.score_flagged, 0.0) AS score_flagged,
                   COALESCE(ms.score_volume, 0.3) AS score_volume,
                   COALESCE(ms.hms_score, 0.5) AS hms_score,
                   ms.last_computed,
                   ms.last_retrieved,
                   COALESCE(ms.decay_rate, 0.023) AS decay_rate
            FROM episodic_memory em
            LEFT JOIN memory_scores ms ON ms.memory_id = em.id
            {where_sql}
            ORDER BY em.timestamp ASC
            """,
            params,
        )


def delete_episodic_memories(database: Path | str) -> int:
    with _get_engine(database).begin() as connection:
        connection.execute(text("DELETE FROM memory_scores"))
        result = connection.execute(text("DELETE FROM episodic_memory"))
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


def mark_session_memory_exported(database: Path | str, session_id: str) -> None:
    with _get_engine(database).begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO session_memory_exports (session_id, exported_at)
                VALUES (:session_id, :exported_at)
                ON CONFLICT(session_id) DO UPDATE SET exported_at = excluded.exported_at
                """
            ),
            {"session_id": session_id, "exported_at": utcnow_iso()},
        )


def is_session_memory_exported(database: Path | str, session_id: str) -> bool:
    with connect(database) as connection:
        row = connection.execute(
            text("SELECT 1 FROM session_memory_exports WHERE session_id = :session_id LIMIT 1"),
            {"session_id": session_id},
        ).first()
    return row is not None


def list_completed_sessions_with_messages_before(
    database: Path | str,
    *,
    ended_before: str,
    limit: int = 500,
) -> list[dict[str, object]]:
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            """
            SELECT s.id, s.started_at, s.ended_at, COUNT(m.id) AS message_count
            FROM sessions s
            JOIN messages m ON m.session_id = s.id
            WHERE s.ended_at IS NOT NULL
              AND s.ended_at < :ended_before
            GROUP BY s.id, s.started_at, s.ended_at
            ORDER BY s.ended_at ASC
            LIMIT :limit
            """,
            {"ended_before": ended_before, "limit": limit},
        )


def delete_session_messages(database: Path | str, session_id: str) -> int:
    with _get_engine(database).begin() as connection:
        result = connection.execute(
            text("DELETE FROM messages WHERE session_id = :session_id"),
            {"session_id": session_id},
        )
    return int(result.rowcount or 0)


def list_user_message_moods_since(
    database: Path | str,
    *,
    moods: tuple[str, ...],
    since: str | None = None,
) -> list[dict[str, object]]:
    if not moods:
        return []
    mood_predicates: list[str] = []
    params: dict[str, object] = {}
    for index, mood in enumerate(moods):
        key = f"mood_{index}"
        mood_predicates.append(f"user_mood = :{key}")
        params[key] = mood
    where_sql = " OR ".join(mood_predicates)
    if since is not None:
        where_sql = f"({where_sql}) AND created_at >= :since"
        params["since"] = since
    with connect(database) as connection:
        return _fetch_dicts(
            connection,
            f"""
            SELECT created_at, user_mood
            FROM messages
            WHERE role = 'user' AND ({where_sql})
            ORDER BY created_at DESC
            """,
            params,
        )
