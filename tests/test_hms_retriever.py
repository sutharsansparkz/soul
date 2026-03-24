from __future__ import annotations

from soul import db
from soul.config import Settings
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.retriever import MemoryRetriever


def _settings(tmp_path) -> Settings:  # noqa: ANN001
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        memory_candidate_k=20,
        memory_retrieval_k=5,
        hms_semantic_weight=0.55,
        hms_score_weight=0.45,
    )


def test_retriever_reranks_with_hms_weight(tmp_path):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings=settings)
    low = repo.add_text(
        "launch plan with investor milestones",
        emotional_tag="neutral",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-10T10:00:00+00:00"},
    )
    high = repo.add_text(
        "launch plan with investor milestones",
        emotional_tag="celebrating",
        metadata={"session_id": "s2", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    repo.boost(str(high.metadata.get("memory_id", high.id)))
    retriever = MemoryRetriever(settings, repo)

    rows = retriever.retrieve(query="launch plan investor", user_id=settings.user_id, k=2, passive=True)

    assert len(rows) >= 1
    top_id = str(rows[0].metadata.get("memory_id", rows[0].id))
    assert top_id == str(high.metadata.get("memory_id", high.id))
    assert str(low.metadata.get("memory_id", low.id)) != ""


def test_retrieval_updates_ref_count_and_last_retrieved(tmp_path):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings=settings)
    created = repo.add_text(
        "stress around launch day and investors",
        emotional_tag="stressed",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    memory_id = str(created.metadata.get("memory_id", created.id))
    before_memory = db.get_episodic_memory(settings.database_url, memory_id)
    before_score = db.get_memory_score(settings.database_url, memory_id)

    MemoryRetriever(settings, repo).retrieve(query="launch investors stress", user_id=settings.user_id, k=1, passive=True)

    after_memory = db.get_episodic_memory(settings.database_url, memory_id)
    after_score = db.get_memory_score(settings.database_url, memory_id)
    assert before_memory is not None and after_memory is not None
    assert int(after_memory["ref_count"]) == int(before_memory["ref_count"]) + 1
    assert before_score is not None and after_score is not None
    assert float(after_score["score_retrieval"]) >= float(before_score["score_retrieval"])
    assert after_score["last_retrieved"] is not None


def test_retriever_filters_out_other_user_memories(tmp_path):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings=settings)
    own = repo.add_text(
        "launch runway planning details",
        emotional_tag="stressed",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    foreign = repo.add_text(
        "launch runway planning details",
        emotional_tag="celebrating",
        metadata={"session_id": "s2", "user_id": "other-user", "timestamp": "2026-03-18T11:00:00+00:00"},
    )

    rows = MemoryRetriever(settings, repo).retrieve(
        query="launch runway planning",
        user_id=settings.user_id,
        k=5,
        passive=True,
    )

    ids = {str(item.metadata.get("memory_id", item.id)) for item in rows}
    assert str(own.metadata.get("memory_id", own.id)) in ids
    assert str(foreign.metadata.get("memory_id", foreign.id)) not in ids


def test_retriever_exposes_bm25_metadata_from_sqlite_fts(tmp_path):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings=settings)
    repo.add_text(
        "investor launch planning runway runway",
        emotional_tag="stressed",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    rows = MemoryRetriever(settings, repo).retrieve(
        query="launch runway",
        user_id=settings.user_id,
        k=1,
        passive=True,
    )
    assert rows
    assert "bm25_raw" in rows[0].metadata
    assert "bm25_score" in rows[0].metadata
    assert "bm25_similarity" in rows[0].metadata
    assert 0.0 <= float(rows[0].metadata["bm25_score"]) <= 1.0


def test_backfill_preserves_ref_count(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    repo = EpisodicMemoryRepository(settings=settings)
    memory_id = "legacy-memory-1"
    repo.add_text(
        "legacy investor launch memory with repeat retrievals",
        emotional_tag="stressed",
        metadata={
            "memory_id": memory_id,
            "session_id": "legacy-session",
            "user_id": settings.user_id,
            "timestamp": "2026-03-18T10:00:00+00:00",
            "ref_count": 5,
        },
    )
    retriever = MemoryRetriever(settings, repo)
    monkeypatch.setattr(retriever, "_apply_retrieval_boost", lambda record: None)

    rows = retriever.retrieve(query="legacy investor launch", user_id=settings.user_id, k=1, passive=True)

    assert rows
    memory_row = db.get_episodic_memory(settings.database_url, memory_id)
    score_row = db.get_memory_score(settings.database_url, memory_id)
    assert memory_row is not None
    assert int(memory_row["ref_count"]) == 5
    assert score_row is not None
    assert float(score_row["score_retrieval"]) >= 0.0
