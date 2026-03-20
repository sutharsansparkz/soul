from __future__ import annotations

import socket
from pathlib import Path
from urllib.error import URLError

from soul.config import Settings
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
