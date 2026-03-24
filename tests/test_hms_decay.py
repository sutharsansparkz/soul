from __future__ import annotations

from datetime import datetime, timezone

from soul import db
from soul.config import Settings
from soul.memory.episodic import EpisodicMemoryRepository


def test_hms_decay_moves_old_memories_to_cold_and_is_idempotent(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        hms_cold_threshold=0.05,
        hms_decay_halflife_days=30.0,
    )
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings=settings)
    created = repo.add_text(
        "small weather remark from long ago",
        emotional_tag="neutral",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2024-01-01T00:00:00+00:00"},
    )
    memory_id = str(created.metadata.get("memory_id", created.id))
    now = datetime(2026, 3, 19, tzinfo=timezone.utc)

    first = repo.decay_all(now=now)
    second = repo.decay_all(now=now)
    row = db.get_episodic_memory(settings.database_url, memory_id)
    score = db.get_memory_score(settings.database_url, memory_id)

    assert first["updated"] >= 1
    assert second["updated"] >= 1
    assert second["moved_to_cold"] == 0
    assert row is not None and row["tier"] == "cold"
    assert score is not None and float(score["hms_score"]) < settings.hms_cold_threshold
