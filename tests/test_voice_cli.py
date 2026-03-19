from __future__ import annotations

from types import SimpleNamespace

from soul import db
from soul.config import Settings
from soul.core.soul_loader import Soul
import soul.cli as cli
from typer.testing import CliRunner


def test_chat_voice_mode_uses_recorded_transcript_before_prompt(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
    )
    spoken: list[str] = []
    captured_messages: list[str] = []
    soul = Soul(
        raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}, "character": {}, "ethics": {}, "worldview": {}},
        name="Ara",
        voice="warm",
        energy="steady",
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))
    monkeypatch.setattr(
        cli.VoiceBridge,
        "record_to_file",
        lambda self, **kwargs: SimpleNamespace(ok=True, output_path=str(tmp_path / "mic.wav"), backend="sounddevice"),
    )
    monkeypatch.setattr(
        cli.VoiceBridge,
        "transcribe",
        lambda self, audio_path, model="base": SimpleNamespace(
            ok=True,
            text="I need a grounded reply from the mic.",
            backend="whisper",
        ),
    )
    monkeypatch.setattr(
        cli.VoiceBridge,
        "speak",
        lambda self, text, output_path=None: spoken.append(text) or SimpleNamespace(
            ok=True,
            output_path=str(tmp_path / "voice.mp3"),
            backend="elevenlabs",
        ),
    )
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(EOFError()))

    def fake_reply(self, *, system_prompt, messages, mood, stream_handler=None):  # noqa: ARG001
        captured_messages.append(messages[-1]["content"])
        if stream_handler is not None:
            stream_handler("reply text")
        return SimpleNamespace(
            text="reply text",
            provider="offline",
            model="mock",
            fallback_used=True,
            error=None,
        )

    monkeypatch.setattr(cli.LLMClient, "reply", fake_reply)

    result = CliRunner().invoke(cli.app, ["chat", "--voice", "--record-seconds", "1"])

    assert result.exit_code == 0
    assert captured_messages == ["I need a grounded reply from the mic."]
    assert spoken == ["reply text"]


def test_chat_voice_mode_reports_recording_and_transcription_failures(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
    )
    soul = Soul(
        raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}, "character": {}, "ethics": {}, "worldview": {}},
        name="Ara",
        voice="warm",
        energy="steady",
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))
    monkeypatch.setattr(
        cli.VoiceBridge,
        "record_to_file",
        lambda self, **kwargs: SimpleNamespace(
            ok=False,
            output_path=None,
            backend="sounddevice",
            error="sounddevice unavailable",
        ),
    )
    monkeypatch.setattr(
        cli.VoiceBridge,
        "transcribe",
        lambda self, audio_path, model="base": SimpleNamespace(
            ok=False,
            text=None,
            backend="whisper",
            error="whisper unavailable",
        ),
    )
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(EOFError()))

    result = CliRunner().invoke(cli.app, ["chat", "--voice", "--record-seconds", "1"])

    assert result.exit_code == 0
    assert "voice recording unavailable" in result.stdout


def test_chat_voice_mode_reports_transcription_failure_for_input_file(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
    )
    soul = Soul(
        raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}, "character": {}, "ethics": {}, "worldview": {}},
        name="Ara",
        voice="warm",
        energy="steady",
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))
    monkeypatch.setattr(
        cli.VoiceBridge,
        "transcribe",
        lambda self, audio_path, model="base": SimpleNamespace(
            ok=False,
            text=None,
            backend="whisper",
            error="whisper unavailable",
        ),
    )
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(EOFError()))

    result = CliRunner().invoke(cli.app, ["chat", "--voice", "--voice-input", str(tmp_path / "missing.wav")])

    assert result.exit_code == 0
    assert "voice transcription unavailable" in result.stdout
