from __future__ import annotations

from datetime import datetime, timezone

from soul import db
from soul.config import Settings
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.scorer import (
    boosted_components,
    compute_composite,
    determine_tier,
    initial_components,
    recompute_components,
)


def test_hms_formula_matches_required_weights():
    value = compute_composite(
        score_emotional=0.8,
        score_retrieval=0.2,
        score_temporal=0.5,
        score_flagged=1.0,
        score_volume=0.5,
    )
    assert round(value, 4) == 0.58


def test_hms_tier_transitions_match_thresholds():
    assert determine_tier(0.90) == "vivid"
    assert determine_tier(0.55) == "present"
    assert determine_tier(0.20) == "fading"
    assert determine_tier(0.01, cold_threshold=0.05) == "cold"


def test_initial_and_boosted_components_recompute_correctly():
    now = datetime(2026, 3, 19, tzinfo=timezone.utc)
    initial = initial_components(
        emotional_tag="venting",
        memory_timestamp="2026-03-18T10:00:00+00:00",
        word_count=40,
        flagged=False,
        now=now,
        half_life_days=30.0,
    )
    boosted = boosted_components(
        emotional_tag="venting",
        memory_timestamp="2026-03-18T10:00:00+00:00",
        word_count=40,
        ref_count=2,
        now=now,
        half_life_days=30.0,
    )
    assert boosted.score_flagged == 1.0
    assert boosted.score_retrieval > initial.score_retrieval
    assert boosted.hms_score > initial.hms_score


def test_recompute_applies_temporal_decay():
    recent = recompute_components(
        emotional_tag="neutral",
        memory_timestamp="2026-03-18T10:00:00+00:00",
        word_count=10,
        ref_count=0,
        flagged=False,
        now=datetime(2026, 3, 19, tzinfo=timezone.utc),
        half_life_days=30.0,
    )
    old = recompute_components(
        emotional_tag="neutral",
        memory_timestamp="2024-03-18T10:00:00+00:00",
        word_count=10,
        ref_count=0,
        flagged=False,
        now=datetime(2026, 3, 19, tzinfo=timezone.utc),
        half_life_days=30.0,
    )
    assert recent.score_temporal > old.score_temporal
    assert recent.hms_score > old.hms_score


def test_add_text_uses_importance_as_emotional_override(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)

    record = repo.add_text(
        "neutral memory that should still be important",
        emotional_tag="neutral",
        importance=0.9,
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-19T10:00:00+00:00"},
    )

    memory_id = str(record.metadata.get("memory_id", record.id))
    score = db.get_memory_score(settings.database_url, memory_id)

    assert score is not None
    assert float(score["score_emotional"]) == 0.9
