from __future__ import annotations

from soul.config import Settings


def test_hms_config_knobs_are_exposed():
    settings = Settings(
        hybrid_embeddings=True,
        hybrid_model="all-MiniLM-L6-v2",
        memory_candidate_k=25,
        hms_semantic_weight=0.6,
        hms_score_weight=0.4,
        hms_decay_halflife_days=45,
        hms_cold_threshold=0.07,
    )
    assert settings.hybrid_embeddings is True
    assert settings.hybrid_model == "all-MiniLM-L6-v2"
    assert settings.memory_candidate_k == 25
    assert settings.hms_semantic_weight == 0.6
    assert settings.hms_score_weight == 0.4
    assert settings.hms_decay_halflife_days == 45
    assert settings.hms_cold_threshold == 0.07


def test_connection_urls_are_redacted_for_cli_output():
    settings = Settings(
        database_url="postgresql://soul_user:db-secret@db.example.com:5432/soul",
        redis_url="redis://:redis-secret@redis.example.com:6379/0",
    )

    payload = settings.as_redacted_dict()

    assert settings.redacted_database_url == "postgresql://***redacted***@db.example.com:5432/soul"
    assert settings.redacted_redis_url == "redis://***redacted***@redis.example.com:6379/0"
    assert payload["database_url"] == settings.redacted_database_url
    assert payload["redis_url"] == settings.redacted_redis_url
    assert "db-secret" not in str(payload["database_url"])
    assert "redis-secret" not in str(payload["redis_url"])
