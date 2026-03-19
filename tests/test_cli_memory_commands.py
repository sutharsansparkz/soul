from __future__ import annotations

from types import SimpleNamespace

from soul import db
from soul.config import Settings
import soul.cli as cli
from soul.memory.episodic import EpisodicMemoryRepository
from typer.testing import CliRunner


def _settings(tmp_path) -> Settings:  # noqa: ANN001
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        chroma_path=str(tmp_path / "chroma"),
        chroma_enabled=False,
    )


def test_memories_list_renders_hms_score_and_tier_bars(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    episodic_repo.add_text(
        "I launched the beta and felt alive.",
        emotional_tag="celebrating",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    result = CliRunner().invoke(cli.app, ["memories"])

    assert result.exit_code == 0
    assert "sorted by HMS score" in result.stdout
    assert "vivid" in result.stdout or "present" in result.stdout
    assert "█" in result.stdout


def test_memories_search_uses_hms_reranked_output(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    first = episodic_repo.add_text(
        "launch strategy for the investor demo",
        emotional_tag="neutral",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-01T10:00:00+00:00"},
    )
    second = episodic_repo.add_text(
        "launch strategy for the investor demo",
        emotional_tag="celebrating",
        metadata={"session_id": "s2", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    episodic_repo.boost(str(second.metadata.get("memory_id", second.id)))
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    result = CliRunner().invoke(cli.app, ["memories", "search", "launch strategy"])

    assert result.exit_code == 0
    assert "HMS reranked" in result.stdout
    assert "Rank" in result.stdout
    assert str(first.content) in result.stdout


def test_memories_search_merges_episodic_and_manual_sources(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    episodic_repo.add_text(
        "launch strategy from emotional memory",
        emotional_tag="celebrating",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    db.save_memory(
        settings.database_url,
        label="manual launch note",
        content="launch strategy checklist for the week",
        importance=0.8,
        source="manual",
    )
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    result = CliRunner().invoke(cli.app, ["memories", "search", "launch strategy"])

    assert result.exit_code == 0
    assert "Unified Memory Search" in result.stdout
    assert "episodic" in result.stdout
    assert "manual" in result.stdout


def test_memories_top_cold_and_boost_commands(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    warm = episodic_repo.add_text(
        "important launch memory",
        emotional_tag="stressed",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2026-03-18T10:00:00+00:00"},
    )
    cold = episodic_repo.add_text(
        "small weather remark",
        emotional_tag="neutral",
        metadata={"session_id": "s1", "user_id": settings.user_id, "timestamp": "2024-03-18T10:00:00+00:00"},
    )
    db.update_episodic_memory_fields(settings.database_url, str(cold.metadata.get("memory_id", cold.id)), tier="cold")
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    top_result = CliRunner().invoke(cli.app, ["memories", "top"])
    cold_result = CliRunner().invoke(cli.app, ["memories", "cold"])
    boost_result = CliRunner().invoke(cli.app, ["memories", "boost", "important launch"])

    assert top_result.exit_code == 0
    assert "Top Memories" in top_result.stdout
    assert cold_result.exit_code == 0
    assert "Cold Memories" in cold_result.stdout
    assert boost_result.exit_code == 0
    assert "Boosted memory" in boost_result.stdout
    boosted = db.get_memory_score(settings.database_url, str(warm.metadata.get("memory_id", warm.id)))
    assert boosted is not None
    assert float(boosted["score_flagged"]) == 1.0


def test_memories_clear_wipes_sql_and_episodic_memory(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    db.save_memory(settings.database_url, label="manual", content="manual memory", importance=0.6)
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    episodic_repo.add_text("episodic memory", importance=0.7, memory_type="moment")

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *args, **kwargs: True))
    result = CliRunner().invoke(cli.app, ["memories", "clear"])

    assert result.exit_code == 0
    assert "SQL memories" in result.stdout
    assert db.list_memories(settings.database_url) == []
    assert db.list_episodic_memories(settings.database_url) == []
