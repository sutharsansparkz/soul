from __future__ import annotations

from types import SimpleNamespace

from soul import db
from soul.config import Settings
import soul.cli as cli
from soul.memory.episodic import EpisodicMemoryRepository
from typer.testing import CliRunner


def test_memories_search_unifies_sql_and_episodic_results(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        chroma_path=str(tmp_path / "chroma"),
        chroma_enabled=False,
    )
    db.init_db(settings.database_url)
    db.save_memory(settings.database_url, label="manual launch note", content="Launch plan with co-founder", importance=0.8)
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    episodic_repo.add_text(
        "We talked about launching the beta next month.",
        importance=0.7,
        memory_type="moment",
        metadata={"timestamp": "2026-03-18T10:00:00+00:00"},
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))
    result = CliRunner().invoke(cli.app, ["memories", "search", "launch"])

    assert result.exit_code == 0
    assert "Semantic Memory Search" in result.stdout
    assert "manual" in result.stdout
    assert "episodic" in result.stdout


def test_memories_clear_wipes_sql_and_episodic_memory(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        chroma_path=str(tmp_path / "chroma"),
        chroma_enabled=False,
    )
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
    assert settings.episodic_memory_file.read_text(encoding="utf-8") == ""
