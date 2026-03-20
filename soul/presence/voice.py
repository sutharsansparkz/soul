from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from soul.config import Settings, get_settings


_HTTP_TIMEOUT_SECONDS: int = 30


@dataclass(slots=True)
class VoiceTranscriptionResult:
    ok: bool
    text: str | None
    backend: str
    error: str | None = None


@dataclass(slots=True)
class VoiceSynthesisResult:
    ok: bool
    output_path: str | None
    backend: str
    error: str | None = None


@dataclass(slots=True)
class VoiceRecordingResult:
    ok: bool
    output_path: str | None
    backend: str
    error: str | None = None


class VoiceBridge:
    """Optional voice adapter with clean degradation when APIs or packages are absent."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        opener: Callable[..., object] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._open = opener or urlopen

    @property
    def elevenlabs_enabled(self) -> bool:
        return bool(self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id)

    def transcribe(self, audio_path: str | Path, *, model: str = "base") -> VoiceTranscriptionResult:
        path = Path(audio_path)
        if not path.exists():
            return VoiceTranscriptionResult(ok=False, text=None, backend="whisper", error=f"missing file: {path}")

        try:
            import whisper
        except Exception as exc:
            return VoiceTranscriptionResult(ok=False, text=None, backend="whisper", error=f"whisper unavailable: {exc}")

        try:
            model_obj = whisper.load_model(model)
            transcript = model_obj.transcribe(str(path))
            text = transcript.get("text", "").strip()
            return VoiceTranscriptionResult(ok=bool(text), text=text or None, backend="whisper")
        except Exception as exc:
            return VoiceTranscriptionResult(ok=False, text=None, backend="whisper", error=str(exc))

    def record_to_file(
        self,
        *,
        seconds: int = 5,
        sample_rate: int = 16_000,
        output_path: str | Path | None = None,
    ) -> VoiceRecordingResult:
        if seconds <= 0:
            return VoiceRecordingResult(ok=False, output_path=None, backend="sounddevice", error="seconds must be > 0")

        try:
            import sounddevice as sd
            import wave
        except Exception as exc:
            return VoiceRecordingResult(ok=False, output_path=None, backend="sounddevice", error=f"sounddevice unavailable: {exc}")

        output = Path(output_path) if output_path else self.settings.soul_data_dir / "voice" / "recording.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            output.parent.chmod(0o700)
        except OSError:
            pass

        try:
            recording = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="int16")
            sd.wait()
            with wave.open(str(output), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(sample_rate)
                handle.writeframes(recording.tobytes())
            try:
                output.chmod(0o600)
            except OSError:
                pass
            return VoiceRecordingResult(ok=True, output_path=str(output), backend="sounddevice")
        except Exception as exc:
            return VoiceRecordingResult(ok=False, output_path=None, backend="sounddevice", error=str(exc))

    def speak(self, text: str, *, output_path: str | Path | None = None) -> VoiceSynthesisResult:
        if not self.elevenlabs_enabled:
            return VoiceSynthesisResult(
                ok=False,
                output_path=None,
                backend="elevenlabs",
                error="missing ElevenLabs credentials",
            )

        output = Path(output_path) if output_path else self.settings.soul_data_dir / "voice" / "latest.mp3"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            output.parent.chmod(0o700)
        except OSError:
            pass

        payload = json.dumps(
            {
                "text": text,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
            },
            ensure_ascii=True,
        ).encode("utf-8")
        request = Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.settings.elevenlabs_voice_id}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": self.settings.elevenlabs_api_key or "",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )

        try:
            with self._open(request, _HTTP_TIMEOUT_SECONDS) as response:
                output.write_bytes(response.read())
            try:
                output.chmod(0o600)
            except OSError:
                pass
            return VoiceSynthesisResult(ok=True, output_path=str(output), backend="elevenlabs")
        except URLError as exc:
            return VoiceSynthesisResult(ok=False, output_path=None, backend="elevenlabs", error=str(exc))
        except Exception as exc:
            return VoiceSynthesisResult(ok=False, output_path=None, backend="elevenlabs", error=str(exc))

    def status(self) -> dict[str, str]:
        return {
            "voice": "enabled" if self.elevenlabs_enabled else "disabled: missing ElevenLabs credentials",
            "transcription": "optional whisper backend",
        }
