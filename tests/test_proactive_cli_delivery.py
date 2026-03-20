from __future__ import annotations

from soul import db
from soul.config import Settings
from soul.core.soul_loader import Soul
import soul.cli as cli
from soul.tasks.proactive import ReachOutCandidate, load_reach_out_candidates, save_reach_out_candidates
from typer.testing import CliRunner


def _settings(tmp_path) -> Settings:  # noqa: ANN001
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )


def _soul() -> Soul:
    return Soul(
        raw={
            "identity": {"name": "Ara", "voice": "warm", "energy": "steady"},
            "character": {},
            "ethics": {},
            "worldview": {},
        },
        name="Ara",
        voice="warm",
        energy="steady",
    )


def test_pending_reach_out_shown_on_chat_start(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    settings.soul_data_dir.mkdir(parents=True, exist_ok=True)
    save_reach_out_candidates(
        settings.reach_out_candidates_file,
        [
            ReachOutCandidate(
                trigger="silence_3_days",
                message="It's been a few days. Just checking in.",
            )
        ],
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, _soul()))
    monkeypatch.setattr(cli, "_refresh_reach_out_candidates", lambda s: None)
    monkeypatch.setattr(
        cli.Prompt,
        "ask",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(EOFError())),
    )

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    assert "It's been a few days" in result.stdout


def test_reach_out_cleared_after_display(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    settings.soul_data_dir.mkdir(parents=True, exist_ok=True)
    save_reach_out_candidates(
        settings.reach_out_candidates_file,
        [ReachOutCandidate(trigger="monday_morning", message="Monday again.")],
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, _soul()))
    monkeypatch.setattr(cli, "_refresh_reach_out_candidates", lambda s: None)
    monkeypatch.setattr(
        cli.Prompt,
        "ask",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(EOFError())),
    )

    CliRunner().invoke(cli.app, ["chat"])

    remaining = load_reach_out_candidates(settings.reach_out_candidates_file)
    assert remaining == []


def test_reach_out_not_shown_when_telegram_configured(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        telegram_bot_token="token",
        telegram_chat_id="12345",
    )
    db.init_db(settings.database_url)
    settings.soul_data_dir.mkdir(parents=True, exist_ok=True)
    save_reach_out_candidates(
        settings.reach_out_candidates_file,
        [ReachOutCandidate(trigger="silence_3_days", message="Checking in.")],
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, _soul()))
    monkeypatch.setattr(cli, "_refresh_reach_out_candidates", lambda s: None)
    monkeypatch.setattr(
        cli.Prompt,
        "ask",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(EOFError())),
    )

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    assert "Checking in." not in result.stdout


def test_no_reach_out_on_empty_candidates(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, _soul()))
    monkeypatch.setattr(cli, "_refresh_reach_out_candidates", lambda s: None)
    monkeypatch.setattr(
        cli.Prompt,
        "ask",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(EOFError())),
    )

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    assert "Just checking in" not in result.stdout
