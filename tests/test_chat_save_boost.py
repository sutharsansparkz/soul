from __future__ import annotations

from types import SimpleNamespace

from soul import db
from soul.config import Settings
from soul.core.soul_loader import Soul
import soul.cli as cli
from typer.testing import CliRunner


def test_in_session_save_command_creates_flagged_hms_memory(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    soul = Soul(
        raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}, "character": {}, "ethics": {}, "worldview": {}},
        name="Ara",
        voice="warm",
        energy="steady",
    )
    prompts = iter(["/save remember this launch moment", "/quit"])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))
    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(lambda *args, **kwargs: next(prompts)))

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    rows = db.search_episodic_memories(settings.database_url, "launch moment", user_id=settings.user_id, include_cold=True, limit=5)
    assert rows
    assert str(rows[0]["content"]) == "remember this launch moment"
    memory_id = str(rows[0]["id"])
    score = db.get_memory_score(settings.database_url, memory_id)
    assert score is not None
    assert float(score["score_flagged"]) == 1.0
