from __future__ import annotations

from soul.config import Settings


def test_hms_config_knobs_are_exposed():
    settings = Settings(
        memory_candidate_k=25,
        hms_semantic_weight=0.6,
        hms_score_weight=0.4,
        hms_decay_halflife_days=45,
        hms_cold_threshold=0.07,
    )
    assert settings.memory_candidate_k == 25
    assert settings.hms_semantic_weight == 0.6
    assert settings.hms_score_weight == 0.4
    assert settings.hms_decay_halflife_days == 45
    assert settings.hms_cold_threshold == 0.07
