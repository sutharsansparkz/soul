from __future__ import annotations

from soul.config import Settings
from soul.memory.episodic import EpisodicMemoryRepository, _INITIALIZED_DATABASES
import soul.persistence.sqlite_setup as sqlite_setup


def test_episodic_repository_initializes_schema_once_per_database(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        _env_file=None,
    )
    calls: list[str] = []

    def fake_initialize_schema(engine):  # noqa: ANN001
        calls.append(str(engine.url))

    monkeypatch.setattr(sqlite_setup, "_initialize_schema", fake_initialize_schema)

    EpisodicMemoryRepository(settings=settings)
    EpisodicMemoryRepository(settings=settings)

    assert calls == [database_url]
    assert database_url in _INITIALIZED_DATABASES
