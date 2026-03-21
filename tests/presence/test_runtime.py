from __future__ import annotations

import pytest

from soul import db
from soul.config import Settings
from soul.core.soul_loader import Soul
from soul.presence.runtime import PresenceRuntime


def test_presence_runtime_closes_session_on_llm_exception(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    runtime = PresenceRuntime(
        settings=settings,
        soul=Soul(
            raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}},
            name="Ara",
            voice="warm",
            energy="steady",
        ),
    )

    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("LLM exploded")

    monkeypatch.setattr(
        runtime.mood_engine,
        "_openai_mood",
        lambda text: ("venting", 0.85, "mock"),
    )
    monkeypatch.setattr(runtime.client, "reply", boom)

    with pytest.raises(RuntimeError, match="LLM exploded"):
        runtime.handle_text("hello")

    sessions = db.list_sessions(settings.database_url, completed_only=True)
    assert len(sessions) == 1
