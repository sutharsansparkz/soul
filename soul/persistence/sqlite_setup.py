"""Schema management for the SQLite-only runtime."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text

from soul.persistence.db import get_engine, utcnow_iso


def ensure_schema(database: str | Path) -> None:
    engine = get_engine(database)
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mood_snapshots (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT,
            message_id TEXT,
            user_mood TEXT NOT NULL,
            companion_state TEXT NOT NULL,
            confidence REAL NOT NULL,
            rationale TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_facts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            fact_type TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            extra_json TEXT NOT NULL DEFAULT '{}',
            score REAL NOT NULL DEFAULT 1.0,
            source TEXT NOT NULL DEFAULT 'runtime',
            observed_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS shared_language_entries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            phrase TEXT NOT NULL,
            meaning TEXT NOT NULL DEFAULT '',
            count INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS personality_state (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            state_json TEXT NOT NULL,
            resonance_signals_json TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'runtime',
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reflection_artifacts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            reflection_key TEXT NOT NULL,
            summary TEXT NOT NULL,
            insights_json TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT 'reflection',
            trace_id TEXT,
            created_at TEXT NOT NULL
            ,
            UNIQUE(user_id, reflection_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS proactive_candidates (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            trigger TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'cli',
            scheduled_for TEXT,
            delivered_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS maintenance_runs (
            id TEXT PRIMARY KEY,
            job_name TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            details_json TEXT NOT NULL DEFAULT '{}',
            error TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS turn_traces (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            input_message_id TEXT,
            reply_message_id TEXT,
            status TEXT NOT NULL DEFAULT 'ok',
            trace_json TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS episodic_memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT,
            label TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            emotional_tag TEXT,
            memory_type TEXT NOT NULL DEFAULT 'moment',
            source TEXT NOT NULL DEFAULT 'auto',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            word_count INTEGER NOT NULL DEFAULT 0,
            flagged INTEGER NOT NULL DEFAULT 0,
            ref_count INTEGER NOT NULL DEFAULT 0,
            tier TEXT NOT NULL DEFAULT 'present',
            score_emotional REAL NOT NULL DEFAULT 0.5,
            score_retrieval REAL NOT NULL DEFAULT 0.0,
            score_temporal REAL NOT NULL DEFAULT 1.0,
            score_flagged REAL NOT NULL DEFAULT 0.0,
            score_volume REAL NOT NULL DEFAULT 0.3,
            hms_score REAL NOT NULL DEFAULT 0.5,
            last_computed TEXT NOT NULL,
            last_retrieved TEXT,
            decay_rate REAL NOT NULL DEFAULT 0.023,
            embedding BLOB,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
    ]

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode = WAL;")
        for statement in statements:
            connection.exec_driver_sql(statement)
        _ensure_existing_tables(connection)
        _migrate_reflection_artifacts_unique_key(connection)
        _ensure_indexes(connection)
        _ensure_fts(connection)


def _migrate_reflection_artifacts_unique_key(connection) -> None:  # type: ignore[no-untyped-def]
    """
    Ensure reflection artifacts are uniquely keyed per user + month key.

    Historical bug: the schema previously enforced `UNIQUE(reflection_key)` only,
    which caused cross-user overwrites when two users generated the same month.
    """

    # If a composite unique constraint already exists (or is created by the current
    # schema), do nothing.
    unique_indexes = connection.execute(text("PRAGMA index_list(reflection_artifacts)")).mappings().all()
    unique_index_columns: list[list[str]] = []
    for idx in unique_indexes:
        if not idx.get("unique"):
            continue
        idx_name = idx.get("name")
        if not idx_name:
            continue
        # SQLite PRAGMAs do not support bound parameters, so inline the index
        # name (it comes from sqlite metadata).
        col_rows = connection.exec_driver_sql(f"PRAGMA index_info('{idx_name}')").fetchall()
        # PRAGMA index_info columns are: seqno, cid, name
        col_names = [str(row[2]) for row in col_rows if row and row[2] is not None]
        unique_index_columns.append(col_names)

    has_composite_unique = any({"user_id", "reflection_key"}.issubset(set(cols)) for cols in unique_index_columns)
    has_reflection_key_only_unique = any(cols == ["reflection_key"] for cols in unique_index_columns)

    if has_composite_unique and not has_reflection_key_only_unique:
        return

    if not has_reflection_key_only_unique:
        # No old single-column uniqueness found; add composite uniqueness via index.
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_reflection_artifacts_user_reflection_unique "
            "ON reflection_artifacts(user_id, reflection_key)"
        )
        return

    # Rebuild the table to drop the old `UNIQUE(reflection_key)` constraint.
    # SQLite doesn't support dropping unique constraints without a rebuild.
    connection.exec_driver_sql(
        """
        CREATE TABLE reflection_artifacts_new (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            reflection_key TEXT NOT NULL,
            summary TEXT NOT NULL,
            insights_json TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT 'reflection',
            trace_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, reflection_key)
        )
        """
    )
    connection.exec_driver_sql(
        """
        INSERT INTO reflection_artifacts_new (
            id, user_id, reflection_key, summary, insights_json, source, trace_id, created_at
        )
        WITH ranked AS (
            SELECT
                id,
                user_id,
                reflection_key,
                summary,
                insights_json,
                source,
                trace_id,
                created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY user_id, reflection_key
                    ORDER BY created_at DESC
                ) AS rn
            FROM reflection_artifacts
        )
        SELECT
            id, user_id, reflection_key, summary, insights_json, source, trace_id, created_at
        FROM ranked
        WHERE rn = 1
        """
    )
    connection.exec_driver_sql("DROP TABLE reflection_artifacts")
    connection.exec_driver_sql("ALTER TABLE reflection_artifacts_new RENAME TO reflection_artifacts")


def _ensure_existing_tables(connection) -> None:  # type: ignore[no-untyped-def]
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    now_iso = utcnow_iso()

    if "sessions" not in tables:
        connection.exec_driver_sql(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                companion_name TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'local-user',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
    else:
        _ensure_columns(
            connection,
            inspector,
            "sessions",
            {
                "user_id": "TEXT NOT NULL DEFAULT 'local-user'",
                "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            },
        )

    if "messages" not in tables:
        connection.exec_driver_sql(
            """
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                user_mood TEXT,
                companion_state TEXT,
                provider TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
            """
        )
    else:
        _ensure_columns(
            connection,
            inspector,
            "messages",
            {
                "provider": "TEXT",
                "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            },
        )

    if "milestones" not in tables:
        connection.exec_driver_sql(
            """
            CREATE TABLE milestones (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                note TEXT NOT NULL,
                session_id TEXT,
                occurred_at TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'relationship',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
    else:
        _ensure_columns(
            connection,
            inspector,
            "milestones",
            {
                "title": "TEXT NOT NULL DEFAULT ''",
                "description": "TEXT NOT NULL DEFAULT ''",
                "category": "TEXT NOT NULL DEFAULT 'relationship'",
                "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
                "created_at": "TEXT",
            },
        )
        connection.execute(
            text(
                """
                UPDATE milestones
                SET title = COALESCE(NULLIF(title, ''), kind),
                    description = COALESCE(NULLIF(description, ''), note),
                    category = COALESCE(NULLIF(category, ''), 'relationship'),
                    metadata_json = COALESCE(NULLIF(metadata_json, ''), '{}'),
                    created_at = COALESCE(NULLIF(created_at, ''), occurred_at, :now_iso)
                """
            ),
            {"now_iso": now_iso},
        )

    if "consolidated_sessions" not in tables:
        connection.exec_driver_sql(
            """
            CREATE TABLE consolidated_sessions (
                session_id TEXT PRIMARY KEY,
                consolidated_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'maintenance'
            )
            """
        )

    if "session_memory_exports" not in tables:
        connection.exec_driver_sql(
            """
            CREATE TABLE session_memory_exports (
                session_id TEXT PRIMARY KEY,
                exported_at TEXT NOT NULL,
                exported_user_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def _ensure_columns(connection, inspector, table_name: str, columns: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name, definition in columns.items():
        if column_name in existing:
            continue
        connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _ensure_indexes(connection) -> None:  # type: ignore[no-untyped-def]
    statements = [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_app_settings_key ON app_settings(key)",
        "CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at ASC)",
        "CREATE INDEX IF NOT EXISTS idx_mood_snapshots_user_created ON mood_snapshots(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_user_facts_user_type_key ON user_facts(user_id, fact_type, key)",
        "CREATE INDEX IF NOT EXISTS idx_shared_language_phrase ON shared_language_entries(user_id, phrase)",
        "CREATE INDEX IF NOT EXISTS idx_personality_state_user_version ON personality_state(user_id, version DESC)",
        "CREATE INDEX IF NOT EXISTS idx_reflection_artifacts_key ON reflection_artifacts(user_id, reflection_key)",
        "CREATE INDEX IF NOT EXISTS idx_proactive_candidates_status ON proactive_candidates(user_id, status, channel, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_maintenance_runs_job ON maintenance_runs(job_name, started_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_turn_traces_session ON turn_traces(session_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_episodic_memories_user_score ON episodic_memories(user_id, hms_score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_episodic_memories_user_tier ON episodic_memories(user_id, tier, observed_at DESC)",
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)


def _ensure_fts(connection) -> None:  # type: ignore[no-untyped-def]
    exists = connection.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'episodic_memories_fts' LIMIT 1")
    ).first()
    connection.exec_driver_sql(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS episodic_memories_fts USING fts5(
            label,
            content,
            emotional_tag,
            memory_type,
            content=episodic_memories,
            content_rowid=rowid,
            tokenize='porter unicode61'
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS episodic_memories_ai AFTER INSERT ON episodic_memories BEGIN
            INSERT INTO episodic_memories_fts(rowid, label, content, emotional_tag, memory_type)
            VALUES (new.rowid, new.label, new.content, new.emotional_tag, new.memory_type);
        END;
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS episodic_memories_au AFTER UPDATE ON episodic_memories BEGIN
            INSERT INTO episodic_memories_fts(episodic_memories_fts, rowid, label, content, emotional_tag, memory_type)
            VALUES ('delete', old.rowid, old.label, old.content, old.emotional_tag, old.memory_type);
            INSERT INTO episodic_memories_fts(rowid, label, content, emotional_tag, memory_type)
            VALUES (new.rowid, new.label, new.content, new.emotional_tag, new.memory_type);
        END;
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS episodic_memories_ad AFTER DELETE ON episodic_memories BEGIN
            INSERT INTO episodic_memories_fts(episodic_memories_fts, rowid, label, content, emotional_tag, memory_type)
            VALUES ('delete', old.rowid, old.label, old.content, old.emotional_tag, old.memory_type);
        END;
        """
    )
    if not exists:
        connection.exec_driver_sql("INSERT INTO episodic_memories_fts(episodic_memories_fts) VALUES('rebuild')")


OBSOLETE_LEGACY_FILENAMES: tuple[str, ...] = (
    "personality.json",
    "user_story.json",
    "drift_log.json",
    "shared_language.json",
    "reach_out_candidates.json",
    "reflections.json",
    "milestones.json",
    "episodic_memory.jsonl",
    "consolidation_ledger.json",
    "proactive_delivery_log.json",
)


def find_obsolete_legacy_files(settings) -> list[Path]:  # type: ignore[no-untyped-def]
    return [
        settings.soul_data_dir / filename
        for filename in OBSOLETE_LEGACY_FILENAMES
        if (settings.soul_data_dir / filename).exists()
    ]
