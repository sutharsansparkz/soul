from __future__ import annotations

import warnings
import socket
from pathlib import Path
from urllib.error import URLError

from soul.config import Settings
import soul.presence.voice as voice_module
from soul.presence.voice import VoiceBridge


def test_voice_bridge_degrades_without_credentials(tmp_path: Path):
    bridge = VoiceBridge()

    synthesis = bridge.speak("hello", output_path=tmp_path / "out.mp3")
    transcript = bridge.transcribe(tmp_path / "missing.wav")

    assert synthesis.ok is False
    assert "missing ElevenLabs credentials" in synthesis.error
    assert transcript.ok is False
    assert "missing file" in transcript.error


def test_voice_bridge_reports_status():
    bridge = VoiceBridge()

    status = bridge.status()

    assert "disabled" in status["voice"]
    assert "whisper" in status["transcription"]


def test_voice_bridge_speak_handles_timeout(tmp_path):
    def timeout_opener(request, timeout=None):  # noqa: ARG001
        raise URLError(socket.timeout("timed out"))

    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        elevenlabs_api_key="fake-key",
        elevenlabs_voice_id="fake-voice",
    )
    bridge = VoiceBridge(settings, opener=timeout_opener)
    result = bridge.speak("hello")

    assert result.ok is False
    assert result.error is not None


def test_voice_bridge_speak_rejects_empty_response(tmp_path):
    class EmptyResponse:
        headers = {"Content-Type": "audio/mpeg"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def read(self):
            return b""

    def empty_opener(request, timeout=None):  # noqa: ARG001
        return EmptyResponse()

    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        elevenlabs_api_key="fake-key",
        elevenlabs_voice_id="fake-voice",
    )
    bridge = VoiceBridge(settings, opener=empty_opener)
    output_path = tmp_path / "latest.mp3"
    result = bridge.speak("hello", output_path=output_path)

    assert result.ok is False
    assert result.error == "empty ElevenLabs response"
    assert not output_path.exists()


def test_voice_bridge_speak_uses_configured_voice_settings(tmp_path):
    captured = {}

    class AudioResponse:
        headers = {"Content-Type": "audio/mpeg"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def read(self):
            return b"audio"

    def opener(request, timeout=None):  # noqa: ARG001
        captured["payload"] = request.data.decode("utf-8")
        return AudioResponse()

    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        elevenlabs_api_key="fake-key",
        elevenlabs_voice_id="fake-voice",
        elevenlabs_voice_stability=0.7,
        elevenlabs_voice_similarity_boost=0.3,
    )
    bridge = VoiceBridge(settings, opener=opener)

    result = bridge.speak("hello", output_path=tmp_path / "latest.mp3")

    assert result.ok is True
    assert '"stability": 0.7' in captured["payload"]
    assert '"similarity_boost": 0.3' in captured["payload"]


def test_voice_bridge_speak_rejects_html_response(tmp_path):
    class HtmlResponse:
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def read(self):
            return b"<html><body>error</body></html>"

    def html_opener(request, timeout=None):  # noqa: ARG001
        return HtmlResponse()

    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        elevenlabs_api_key="fake-key",
        elevenlabs_voice_id="fake-voice",
    )
    bridge = VoiceBridge(settings, opener=html_opener)
    output_path = tmp_path / "latest.mp3"

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        result = bridge.speak("hello", output_path=output_path)

    assert result.ok is False
    assert "unexpected ElevenLabs content-type" in result.error
    assert not output_path.exists()
    assert any("unexpected content-type" in str(item.message) for item in captured)


def test_voice_bridge_play_returns_false_when_no_player_found(monkeypatch, tmp_path):
    bridge = VoiceBridge()
    audio_path = tmp_path / "reply.mp3"
    audio_path.write_bytes(b"fake audio")

    monkeypatch.setattr(voice_module.sys, "platform", "linux")

    def missing_player(*args, **kwargs):  # noqa: ANN001, ARG001
        raise FileNotFoundError("player not found")

    monkeypatch.setattr(voice_module.subprocess, "run", missing_player)

    assert bridge.play(audio_path) is False
