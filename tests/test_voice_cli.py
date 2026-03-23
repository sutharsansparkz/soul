from __future__ import annotations

from types import SimpleNamespace

from soul import db
from soul.config import Settings
from soul.core.soul_loader import Soul, load_soul
import soul.cli as cli
from typer.testing import CliRunner


import pytest


@pytest.mark.live_llm
def test_chat_voice_mode_uses_recorded_transcript_before_prompt(tmp_path, monkeypatch, live_llm_requested, request):
    if live_llm_requested:
        settings = request.getfixturevalue("live_llm_runtime_settings")
        db.init_db(settings.database_url)
        soul = load_soul(settings.soul_file)
        spoken: list[str] = []

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
                text="Reply with LIVE_MIC_OK in one short sentence.",
                backend="whisper",
            ),
        )
        monkeypatch.setattr(
            cli.VoiceBridge,
            "speak",
            lambda self, text, output_path=None, autoplay=False: spoken.append(text) or SimpleNamespace(
                ok=True,
                output_path=str(tmp_path / "voice.mp3"),
                backend="elevenlabs",
                played=True,
            ),
        )
        monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(EOFError()))

        result = CliRunner().invoke(cli.app, ["chat", "--voice", "--record-seconds", "1"])

        assert result.exit_code == 0
        assert "LIVE_MIC_OK" in result.stdout
        session_id = db.get_last_completed_session_id(settings.database_url)
        rows = db.get_session_messages(settings.database_url, session_id)
        assert any(row["role"] == "user" and "LIVE_MIC_OK" in str(row["content"]) for row in rows)
        assert any(row["role"] == "assistant" and row["provider"] == "openai" for row in rows)
        assert spoken
        return

    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
        _env_file=None,
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
        lambda self, text, output_path=None, autoplay=False: spoken.append(text) or SimpleNamespace(
            ok=True,
            output_path=str(tmp_path / "voice.mp3"),
            backend="elevenlabs",
        ),
    )
    monkeypatch.setattr(
        cli.MoodEngine,
        "_openai_mood",
        lambda self, text: ("reflective", 0.85, "mock"),
    )
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(EOFError()))

    def fake_reply(self, *, system_prompt, messages, mood, stream_handler=None):  # noqa: ARG001
        captured_messages.append(messages[-1]["content"])
        if stream_handler is not None:
            stream_handler("reply text")
        return SimpleNamespace(
            text="reply text",
            provider="mock-openai",
            model="mock",
            fallback_used=False,
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


@pytest.mark.live_llm
def test_voice_command_toggles_both_input_and_output(tmp_path, monkeypatch, live_llm_requested, request):
    if live_llm_requested:
        settings = request.getfixturevalue("live_llm_runtime_settings")
        db.init_db(settings.database_url)
        soul = load_soul(settings.soul_file)
        recorded_seconds: list[int] = []
        spoken: list[str] = []
        prompts = iter(["/voice off", "/voice on", "", "/voice off", "Reply with LIVE_TYPED_OK in one short sentence.", "/quit"])

        monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))
        monkeypatch.setattr(cli.VoiceBridge, "can_record", property(lambda self: True))
        monkeypatch.setattr(
            cli.VoiceBridge,
            "record_to_file",
            lambda self, **kwargs: recorded_seconds.append(int(kwargs["seconds"])) or SimpleNamespace(
                ok=True,
                output_path=str(tmp_path / "mic.wav"),
                backend="sounddevice",
            ),
        )
        monkeypatch.setattr(
            cli.VoiceBridge,
            "transcribe",
            lambda self, audio_path, model="base": SimpleNamespace(
                ok=True,
                text="Reply with LIVE_VOICE_TOGGLE_OK in one short sentence.",
                backend="whisper",
            ),
        )
        monkeypatch.setattr(
            cli.VoiceBridge,
            "speak",
            lambda self, text, output_path=None, autoplay=False: spoken.append(text) or SimpleNamespace(
                ok=True,
                output_path=str(tmp_path / "voice.mp3"),
                backend="elevenlabs",
                played=True,
            ),
        )
        monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: next(prompts))

        result = CliRunner().invoke(cli.app, ["chat", "--voice"])

        assert result.exit_code == 0
        assert recorded_seconds == [6]
        assert "LIVE_VOICE_TOGGLE_OK" in result.stdout
        assert "LIVE_TYPED_OK" in result.stdout
        assert len(spoken) == 1
        session_id = db.get_last_completed_session_id(settings.database_url)
        rows = db.get_session_messages(settings.database_url, session_id)
        assert any(row["role"] == "assistant" and row["provider"] == "openai" for row in rows)
        return

    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
        _env_file=None,
    )
    soul = Soul(
        raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}, "character": {}, "ethics": {}, "worldview": {}},
        name="Ara",
        voice="warm",
        energy="steady",
    )
    recorded_seconds: list[int] = []
    spoken: list[str] = []
    captured_messages: list[str] = []
    prompts = iter(["/voice off", "/voice on", "", "/voice off", "typed after off", "/quit"])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))
    monkeypatch.setattr(cli.VoiceBridge, "can_record", property(lambda self: True))
    monkeypatch.setattr(
        cli.VoiceBridge,
        "record_to_file",
        lambda self, **kwargs: recorded_seconds.append(int(kwargs["seconds"])) or SimpleNamespace(
            ok=True,
            output_path=str(tmp_path / "mic.wav"),
            backend="sounddevice",
        ),
    )
    monkeypatch.setattr(
        cli.VoiceBridge,
        "transcribe",
        lambda self, audio_path, model="base": SimpleNamespace(
            ok=True,
            text="spoken after re-enable",
            backend="whisper",
        ),
    )
    monkeypatch.setattr(
        cli.VoiceBridge,
        "speak",
        lambda self, text, output_path=None, autoplay=False: spoken.append(text) or SimpleNamespace(
            ok=True,
            output_path=str(tmp_path / "voice.mp3"),
            backend="elevenlabs",
        ),
    )
    monkeypatch.setattr(
        cli.MoodEngine,
        "_openai_mood",
        lambda self, text: ("reflective", 0.85, "mock"),
    )
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: next(prompts))

    def fake_reply(self, *, system_prompt, messages, mood, stream_handler=None):  # noqa: ARG001
        captured_messages.append(messages[-1]["content"])
        if stream_handler is not None:
            stream_handler(f"reply to {messages[-1]['content']}")
        return SimpleNamespace(
            text=f"reply to {messages[-1]['content']}",
            provider="mock-openai",
            model="mock",
            fallback_used=False,
            error=None,
        )

    monkeypatch.setattr(cli.LLMClient, "reply", fake_reply)

    result = CliRunner().invoke(cli.app, ["chat", "--voice"])

    assert result.exit_code == 0
    assert recorded_seconds == [6]
    assert captured_messages == ["spoken after re-enable", "typed after off"]
    assert spoken == ["reply to spoken after re-enable"]
    assert "Voice input and output disabled for this session." in result.stdout
    assert "Voice input and output enabled for this session." in result.stdout


def test_voice_output_uses_autoplay_flag():
    captured: dict[str, object] = {}

    class FakeVoiceBridge:
        def speak(self, text, *, output_path=None, autoplay=False):  # noqa: ANN001, ARG002
            captured["text"] = text
            captured["autoplay"] = autoplay
            return SimpleNamespace(ok=True, output_path="voice.mp3", backend="elevenlabs", played=True)

    cli._voice_output(FakeVoiceBridge(), True, "hello")

    assert captured == {"text": "hello", "autoplay": True}


def test_chat_handles_malformed_quoted_slash_command_without_crashing(tmp_path, monkeypatch):
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
    prompts = iter(['/voice "', '/quit'])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: next(prompts))

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    assert "Invalid command syntax" in result.stdout
    assert "No closing quotation" in result.stdout
