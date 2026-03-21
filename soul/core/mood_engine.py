from __future__ import annotations

import json
import re
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from typing import Any

from soul.config import Settings

_LOCAL_STATE_CACHE: dict[str, dict] = {}
_CLASSIFIER_NOTICE_SHOWN = False
_CLASSIFIER_DOWNLOAD_NOTICE_SHOWN = False
_CLASSIFIER_LOAD_NOTICE_SHOWN = False


@dataclass(slots=True)
class MoodSnapshot:
    user_mood: str
    companion_state: str
    confidence: float
    rationale: str


class MoodEngine:
    """Mood detection with optional transformers + Redis-backed companion state."""

    USER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("overwhelmed", ("can't do this", "cannot do this", "too much", "overwhelmed", "shut down", "numb")),
        ("stressed", ("stress", "stressed", "anxious", "panic", "worried", "pressure")),
        ("celebrating", ("excited", "happy", "amazing", "won", "great news", "celebrate", "thrilled")),
        ("curious", ("how do you", "what do you think", "why does", "tell me about")),
        ("reflective", ("meaning", "wondering", "thinking about", "late night", "who am i")),
        ("venting", ("rough day", "awful", "hate this", "frustrated", "angry", "invisible", "hurt")),
    )

    STATE_MAP = {
        "overwhelmed": "quiet",
        "stressed": "concerned",
        "celebrating": "playful",
        "curious": "curious",
        "reflective": "reflective",
        "venting": "warm",
        "neutral": "neutral",
    }

    # Exact 7 labels output by cardiffnlp/twitter-roberta-base-emotion.
    # Do not add labels from other models (e.g. go-emotions) — they will never match.
    MODEL_LABEL_MAP = {
        "anger": "venting",
        "disgust": "venting",
        "fear": "stressed",
        "joy": "celebrating",
        "sadness": "overwhelmed",
        "surprise": "curious",
        "neutral": "neutral",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def analyze(self, text: str, user_id: str | None = None, now: datetime | None = None) -> MoodSnapshot:
        now = now or datetime.now(timezone.utc)
        user_id = user_id or self.settings.user_id

        model_result = self._model_mood(text)
        if model_result:
            user_mood, confidence, rationale = model_result
        else:
            user_mood, confidence, rationale = self._heuristic_mood(text, now)

        previous_state = self.current_state(user_id)
        if user_mood == "neutral" and not self._should_preserve_previous_state(text):
            previous_state = None
        companion_state = self._select_companion_state(user_mood, previous_state, now)
        self._persist_state(
            user_id=user_id,
            payload={
                "state": companion_state,
                "last_user_mood": user_mood,
                "updated_at": now.isoformat(),
            },
        )
        return MoodSnapshot(
            user_mood=user_mood,
            companion_state=companion_state,
            confidence=confidence,
            rationale=rationale,
        )

    def _should_preserve_previous_state(self, text: str) -> bool:
        return len(text.split()) <= 4

    def current_state(self, user_id: str | None = None) -> dict[str, Any] | None:
        user_id = user_id or self.settings.user_id
        raw: str | None = None
        if self.redis_client is not None:
            try:
                raw = self.redis_client.get(self._redis_key(user_id))
            except Exception:
                raw = None
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        cached = _LOCAL_STATE_CACHE.get(user_id)
        return dict(cached) if cached is not None else None

    def _select_companion_state(
        self,
        user_mood: str,
        previous_state: dict[str, Any] | None,
        now: datetime,
    ) -> str:
        if user_mood != "neutral":
            return self.STATE_MAP[user_mood]

        if previous_state:
            updated_at = previous_state.get("updated_at")
            try:
                previous_dt = datetime.fromisoformat(updated_at)
            except (TypeError, ValueError):
                previous_dt = None
            if previous_dt is not None:
                hours = (now - previous_dt).total_seconds() / 3600
                if hours < self.settings.mood_decay_hours:
                    return str(previous_state.get("state") or "neutral")

        return "neutral"

    def _heuristic_mood(self, text: str, now: datetime) -> tuple[str, float, str]:
        lowered = text.casefold()

        for mood, needles in self.USER_RULES:
            if any(re.search(rf"\b{re.escape(needle)}\b", lowered) for needle in needles):
                return mood, 0.77, f"matched heuristic keywords for {mood}"

        if len(text.split()) <= 4 and any(word in lowered for word in ("tired", "done", "ugh")):
            return "overwhelmed", 0.7, "short exhausted phrasing"

        if "?" in text and len(text.split()) > 5:
            return "curious", 0.62, "question-led prompt"

        if now.hour >= 23 or now.hour < 5:
            return "reflective", 0.58, "late-night default"

        return "neutral", 0.45, "fallback neutral classification"

    def _model_mood(self, text: str) -> tuple[str, float, str] | None:
        classifier = self.classifier
        if classifier is None:
            return None

        try:
            result = classifier(text, truncation=True)
        except TypeError:
            result = classifier(text)
        except Exception:
            return None

        scores = result[0] if result and isinstance(result[0], list) else result
        if not scores:
            return None

        top = max(scores, key=lambda item: item.get("score", 0.0))
        label = str(top.get("label", "")).casefold()
        mapped = self.MODEL_LABEL_MAP.get(label)
        if not mapped:
            return None
        return mapped, float(top.get("score", 0.0)), f"transformers model label={label}"

    def _persist_state(self, *, user_id: str, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=True)
        if self.redis_client is not None:
            try:
                self.redis_client.set(self._redis_key(user_id), serialized)
            except Exception:
                _LOCAL_STATE_CACHE[user_id] = dict(payload)
                return
        _LOCAL_STATE_CACHE[user_id] = dict(payload)

    def _redis_key(self, user_id: str) -> str:
        return f"{self.settings.redis_key_prefix}:mood:{user_id}"

    @cached_property
    def redis_client(self):  # type: ignore[no-untyped-def]
        try:
            import redis
        except ImportError:
            return None

        try:
            return redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
        except Exception:
            return None

    @cached_property
    def classifier(self):  # type: ignore[no-untyped-def]
        global _CLASSIFIER_NOTICE_SHOWN, _CLASSIFIER_DOWNLOAD_NOTICE_SHOWN, _CLASSIFIER_LOAD_NOTICE_SHOWN
        if not self.settings.mood_model_enabled:
            return None
        try:
            from transformers import pipeline
        except ImportError:
            if not _CLASSIFIER_NOTICE_SHOWN:
                warnings.warn(
                    "Mood classifier is enabled (MOOD_MODEL_ENABLED=true) but 'transformers' "
                    "is not installed. Falling back to keyword heuristics. "
                    "Install with: pip install transformers torch  "
                    "OR disable the model with: MOOD_MODEL_ENABLED=false",
                    stacklevel=2,
                )
                _CLASSIFIER_NOTICE_SHOWN = True
            return None
        try:
            model_name = self.settings.mood_model_name
            try:
                from huggingface_hub import try_to_load_from_cache

                cached = try_to_load_from_cache(model_name, "config.json")
                already_cached = isinstance(cached, str)
            except Exception:
                already_cached = False

            if not already_cached and not _CLASSIFIER_DOWNLOAD_NOTICE_SHOWN:
                print(
                    f"[soul] Downloading mood model {model_name!r} (~500 MB). "
                    "Set MOOD_MODEL_ENABLED=false to skip.",
                    file=sys.stderr,
                    flush=True,
                )
                _CLASSIFIER_DOWNLOAD_NOTICE_SHOWN = True

            clf = pipeline(
                "text-classification",
                model=model_name,
                return_all_scores=True,
            )
            if not _CLASSIFIER_LOAD_NOTICE_SHOWN:
                print(
                    "[soul] Mood classifier loaded (cardiffnlp/twitter-roberta-base-emotion). "
                    "Set MOOD_MODEL_ENABLED=false to disable.",
                    file=sys.stderr,
                )
                _CLASSIFIER_LOAD_NOTICE_SHOWN = True
            return clf
        except Exception:
            return None
