from __future__ import annotations

from pathlib import Path

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
