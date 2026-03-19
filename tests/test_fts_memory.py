from __future__ import annotations

from soul import db
from soul.config import Settings
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.fts import search_fts


def _settings(tmp_path) -> Settings:  # noqa: ANN001
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        chroma_path=str(tmp_path / "chroma"),
        chroma_enabled=False,
    )


def test_sqlite_fts_search_returns_ranked_candidates(tmp_path):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    repo.add_text(
        "launch planning for investor runway",
        emotional_tag="stressed",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    repo.add_text(
        "weather was calm yesterday",
        emotional_tag="neutral",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-17T10:00:00+00:00"},
    )

    rows = search_fts(
        settings.database_url,
        "launch runway",
        user_id=settings.user_id,
        include_cold=True,
        limit=20,
    )

    assert rows
    assert "bm25_score" in rows[0]
    assert "launch" in str(rows[0]["content"]).casefold()


def test_sqlite_fts_query_sanitization_handles_symbols(tmp_path):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    repo.add_text(
        "investor update with launch notes",
        emotional_tag="curious",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )

    rows = db.search_episodic_memories_fts(
        settings.database_url,
        "launch!!! ### ???",
        user_id=settings.user_id,
        include_cold=True,
        limit=20,
    )

    assert rows
