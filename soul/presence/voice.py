from __future__ import annotations

import json
import os
import subprocess
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from soul.config import Settings, get_settings


@dataclass(slots=True)
class VoiceTranscriptionResult:
    ok: bool
    text: str | None
    backend: str
    error: str | None = None


@dataclass(slots=True)
class VoicePlaybackResult:
    ok: bool
    backend: str
    error: str | None = None


@dataclass(slots=True)
class VoiceSynthesisResult:
    ok: bool
    output_path: str | None
    backend: str
    error: str | None = None
    played: bool = False


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
        self._http_timeout = self.settings.elevenlabs_http_timeout

    @property
    def elevenlabs_enabled(self) -> bool:
        return bool(self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id)

    @property
    def can_record(self) -> bool:
        try:
            import sounddevice  # noqa: F401
            return True
        except Exception:
            return False

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
        except OSError as exc:
            warnings.warn(f"Could not set permissions on {output}: {exc}")

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
            except OSError as exc:
                warnings.warn(f"Could not set permissions on {output}: {exc}")
            return VoiceRecordingResult(ok=True, output_path=str(output), backend="sounddevice")
        except Exception as exc:
            return VoiceRecordingResult(ok=False, output_path=None, backend="sounddevice", error=str(exc))

    def play(self, audio_path: str | Path) -> bool:
        return self._playback_result(audio_path).ok

    def speak(
        self,
        text: str,
        *,
        output_path: str | Path | None = None,
        autoplay: bool = False,
    ) -> VoiceSynthesisResult:
        if not self.elevenlabs_enabled:
            return VoiceSynthesisResult(
                ok=False,
                output_path=None,
                backend="elevenlabs",
                error="missing ElevenLabs credentials",
                played=False,
            )

        output = Path(output_path) if output_path else self.settings.soul_data_dir / "voice" / "latest.mp3"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            output.parent.chmod(0o700)
        except OSError as exc:
            warnings.warn(f"Could not set permissions on {output}: {exc}")

        payload = json.dumps(
            {
                "text": text,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
            },
            ensure_ascii=True,
        ).encode("utf-8")
        api_key = self.settings.elevenlabs_api_key.get_secret_value() if self.settings.elevenlabs_api_key else ""
        request = Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.settings.elevenlabs_voice_id}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": api_key,
                "Accept": "audio/mpeg",
            },
            method="POST",
        )

        try:
            with self._open(request, self._http_timeout) as response:
                content_type = ""
                if hasattr(response, "headers") and response.headers:
                    content_type = response.headers.get("Content-Type", "")
                audio_bytes = response.read()

            if not audio_bytes:
                return VoiceSynthesisResult(
                    ok=False,
                    output_path=None,
                    backend="elevenlabs",
                    error="empty ElevenLabs response",
                    played=False,
                )

            if content_type and not content_type.lower().startswith("audio/"):
                warnings.warn(
                    f"ElevenLabs returned unexpected content-type: {content_type!r}. "
                    "Response may be an error page.",
                    stacklevel=2,
                )
                return VoiceSynthesisResult(
                    ok=False,
                    output_path=None,
                    backend="elevenlabs",
                    error=f"unexpected ElevenLabs content-type: {content_type}",
                    played=False,
                )

            output.write_bytes(audio_bytes)
            try:
                output.chmod(0o600)
            except OSError as exc:
                warnings.warn(f"Could not set permissions on {output}: {exc}")
            played = self.play(output) if autoplay else False
            return VoiceSynthesisResult(ok=True, output_path=str(output), backend="elevenlabs", played=played)
        except URLError as exc:
            return VoiceSynthesisResult(ok=False, output_path=None, backend="elevenlabs", error=str(exc), played=False)
        except Exception as exc:
            return VoiceSynthesisResult(ok=False, output_path=None, backend="elevenlabs", error=str(exc), played=False)

    def _playback_result(self, audio_path: str | Path) -> VoicePlaybackResult:
        path = Path(audio_path)
        if not path.exists():
            return VoicePlaybackResult(ok=False, backend="file", error=f"missing file: {path}")

        if sys.platform == "darwin":
            return self._run_player(["afplay", str(path)], backend="afplay")
        if sys.platform == "win32":
            try:
                os.startfile(str(path))
                return VoicePlaybackResult(ok=True, backend="os.startfile")
            except OSError as exc:
                return VoicePlaybackResult(ok=False, backend="os.startfile", error=str(exc))

        last_result = VoicePlaybackResult(ok=False, backend="aplay", error="no playback backend succeeded")
        for backend, command in (
            ("aplay", ["aplay", str(path)]),
            ("mpg123", ["mpg123", str(path)]),
            ("ffplay", ["ffplay", "-nodisp", "-autoexit", str(path)]),
        ):
            result = self._run_player(command, backend=backend)
            if result.ok:
                return result
            last_result = result
        return last_result

    def _run_player(self, command: list[str], *, backend: str) -> VoicePlaybackResult:
        try:
            completed = subprocess.run(command, timeout=60, capture_output=True)
        except FileNotFoundError:
            return VoicePlaybackResult(ok=False, backend=backend, error=f"{backend} not installed")
        except subprocess.TimeoutExpired as exc:
            return VoicePlaybackResult(ok=False, backend=backend, error=str(exc))
        except OSError as exc:
            return VoicePlaybackResult(ok=False, backend=backend, error=str(exc))

        if completed.returncode == 0:
            return VoicePlaybackResult(ok=True, backend=backend)
        return VoicePlaybackResult(ok=False, backend=backend, error=f"{backend} exited with code {completed.returncode}")

    def status(self) -> dict[str, str]:
        return {
            "voice": "enabled" if self.elevenlabs_enabled else "disabled: missing ElevenLabs credentials",
            "transcription": "optional whisper backend",
        }
