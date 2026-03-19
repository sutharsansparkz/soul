from __future__ import annotations

from datetime import datetime, timezone

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
