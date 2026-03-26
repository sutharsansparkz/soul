from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from soul.config import Settings
from soul.memory.repositories.mood import MoodSnapshotsRepository
from soul.persistence.sqlite_setup import ensure_schema

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MoodSnapshot:
    user_mood: str
    companion_state: str
    confidence: float
    rationale: str


class MoodEngine:
    """Mood detection via OpenAI with SQLite-backed companion state."""

    STATE_MAP = {
        "overwhelmed": "quiet",
        "stressed": "concerned",
        "celebrating": "playful",
        "curious": "curious",
        "reflective": "reflective",
        "venting": "warm",
        "neutral": "neutral",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        ensure_schema(self.settings.database_url)
        self.repository = MoodSnapshotsRepository(
            self.settings.database_url,
            user_id=self.settings.user_id,
        )
        self._openai_client = None

    def _get_openai_client(self):  # type: ignore[no-untyped-def]
        if self._openai_client is None:
            if not self.settings.openai_api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is required for mood classification. Set it in your .env file."
                )
            from openai import OpenAI
            self._openai_client = OpenAI(
                api_key=self.settings.openai_api_key.get_secret_value(),
                base_url=self.settings.openai_base_url or None,
            )
        return self._openai_client

    def analyze(
        self,
        text: str,
        user_id: str | None = None,
        now: datetime | None = None,
        *,
        persist: bool = True,
        session_id: str | None = None,
        message_id: str | None = None,
    ) -> MoodSnapshot:
        now = now or datetime.now(timezone.utc)
        user_id = user_id or self.settings.user_id
        repository = (
            MoodSnapshotsRepository(self.settings.database_url, user_id=user_id)
            if user_id != self.settings.user_id
            else self.repository
        )

        try:
            user_mood, confidence, rationale = self._openai_mood(text)
        except RuntimeError as exc:
            # Misconfiguration: fail fast (e.g., missing OPENAI_API_KEY).
            if "OPENAI_API_KEY is required" in str(exc):
                raise
            _logger.warning("Mood classification runtime error; falling back to neutral: %s", exc)
            user_mood = "neutral"
            confidence = 0.0
            rationale = f"mood classification failed: {type(exc).__name__}"
        except Exception as exc:
            _logger.warning("Mood classification failed; falling back to neutral: %s", exc)
            user_mood = "neutral"
            confidence = 0.0
            rationale = f"mood classification failed: {type(exc).__name__}"

        previous_state = self.current_state(user_id)
        if user_mood == "neutral" and not self._should_preserve_previous_state(text):
            previous_state = None
        companion_state = self._select_companion_state(user_mood, previous_state, now)
        snapshot = MoodSnapshot(
            user_mood=user_mood,
            companion_state=companion_state,
            confidence=confidence,
            rationale=rationale,
        )
        if persist:
            repository.add_snapshot(
                session_id=session_id,
                message_id=message_id,
                user_mood=snapshot.user_mood,
                companion_state=snapshot.companion_state,
                confidence=snapshot.confidence,
                rationale=snapshot.rationale,
                created_at=now.replace(microsecond=0).isoformat(),
            )
        return snapshot

    def _openai_mood(self, text: str) -> tuple[str, float, str]:
        client = self._get_openai_client()
        valid = self.settings.mood_valid_labels
        labels_str = ", ".join(valid)
        valid_set = {str(label).casefold() for label in valid}
        prompt = (
            "Classify the emotional mood of the following user message.\n"
            'Return JSON only: {"mood": "<label>", "confidence": <0.0-1.0>}\n'
            f"Valid mood labels: {labels_str}\n"
            f'Message: "{text}"'
        )

        response = client.chat.completions.create(
            model=self.settings.mood_openai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.settings.mood_openai_max_tokens,
            temperature=self.settings.mood_openai_temperature,
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            _logger.warning("Mood classification from OpenAI returned empty content.")
            return "neutral", 0.0, "empty openai response"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start < 0 or end <= start:
                _logger.warning("Could not decode mood classification from OpenAI: %r", raw)
                return "neutral", 0.0, f"could not decode openai response: {raw!r}"
            try:
                payload = json.loads(raw[start:end])
            except json.JSONDecodeError:
                _logger.warning("Could not decode mood classification from OpenAI: %r", raw)
                return "neutral", 0.0, f"could not decode openai response: {raw!r}"
        mood = str(payload.get("mood", "")).casefold()
        if mood not in valid_set:
            mood = "neutral"
        if mood not in self.STATE_MAP:
            # Configured label may exist but doesn't map to a companion state.
            mood = "neutral"

        try:
            confidence = float(payload.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        confidence = max(0.0, min(1.0, confidence))
        return mood, confidence, f"openai mood prompt (model={self.settings.mood_openai_model})"

    def _should_preserve_previous_state(self, text: str) -> bool:
        return len(text.split()) <= self.settings.mood_preserve_previous_max_words

    def current_state(self, user_id: str | None = None) -> dict[str, object] | None:
        if user_id and user_id != self.settings.user_id:
            return MoodSnapshotsRepository(self.settings.database_url, user_id=user_id).current_state()
        return self.repository.current_state()

    def _select_companion_state(
        self,
        user_mood: str,
        previous_state: dict[str, object] | None,
        now: datetime,
    ) -> str:
        if user_mood != "neutral":
            return self.STATE_MAP[user_mood]

        if previous_state:
            updated_at = previous_state.get("updated_at")
            try:
                previous_dt = datetime.fromisoformat(str(updated_at))
            except (TypeError, ValueError):
                previous_dt = None
            if previous_dt is not None:
                hours = (now - previous_dt).total_seconds() / 3600
                if hours < self.settings.mood_decay_hours:
                    return str(previous_state.get("state") or "neutral")

        return "neutral"
