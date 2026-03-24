from __future__ import annotations

from soul import db
from sqlalchemy import inspect, text


def test_init_db_migrates_legacy_hms_tables_with_defaults(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"

    with db.connect(database_url) as connection:
        connection.execute(
            text(
                """
                CREATE TABLE episodic_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    content TEXT NOT NULL,
                    emotional_tag TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE memory_scores (
                    memory_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO episodic_memory (id, user_id, session_id, timestamp, content, emotional_tag)
                VALUES ('mem-1', 'local-user', 's1', '2026-03-19T10:00:00+00:00', 'legacy content', 'neutral')
                """
            )
        )
        connection.execute(
            text("INSERT INTO memory_scores (memory_id, user_id) VALUES ('mem-1', 'local-user')")
        )
        connection.commit()

    db.init_db(database_url)

    with db.connect(database_url) as connection:
        inspector = inspect(connection)
        episodic_columns = {item["name"] for item in inspector.get_columns("episodic_memory")}
        score_columns = {item["name"] for item in inspector.get_columns("memory_scores")}
        fts_exists = connection.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory_fts' LIMIT 1")
        ).first()

    assert {"word_count", "flagged", "ref_count", "tier", "memory_type", "embedding"} <= episodic_columns
    assert {
        "score_emotional",
        "score_retrieval",
        "score_temporal",
        "score_flagged",
        "score_volume",
        "hms_score",
        "last_computed",
        "last_retrieved",
        "decay_rate",
    } <= score_columns
    assert fts_exists is not None

    memory_row = db.get_episodic_memory(database_url, "mem-1")
    score_row = db.get_memory_score(database_url, "mem-1")
    assert memory_row is not None
    assert int(memory_row["word_count"]) == 0
    assert int(memory_row["flagged"]) == 0
    assert int(memory_row["ref_count"]) == 0
    assert str(memory_row["tier"]) == "present"
    assert str(memory_row["memory_type"]) == "moment"
    assert score_row is not None
    assert float(score_row["hms_score"]) == 0.5
    assert score_row["last_computed"] is not None

    fts_rows = db.search_episodic_memories_fts(database_url, "legacy", user_id="local-user", include_cold=True, limit=5)
    assert fts_rows


def test_clear_memories_removes_orphaned_memory_scores(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)
    db.save_memory(database_url, label="manual", content="manual note", importance=0.6)
    memory_id = db.create_episodic_memory(
        database_url,
        user_id="local-user",
        session_id="s1",
        content="episodic note",
        timestamp="2026-03-19T10:00:00+00:00",
    )
    db.upsert_memory_score(
        database_url,
        memory_id=memory_id,
        user_id="local-user",
        score_emotional=0.5,
        score_retrieval=0.0,
        score_temporal=1.0,
        score_flagged=0.0,
        score_volume=0.3,
        hms_score=0.5,
    )

    with db.connect(database_url) as connection:
        connection.execute(text("DELETE FROM episodic_memory WHERE id = :memory_id"), {"memory_id": memory_id})
        connection.commit()

    deleted = db.clear_memories(database_url)

    assert deleted == 2
    assert db.list_memories(database_url) == []
    assert db.get_memory_score(database_url, memory_id) is None
