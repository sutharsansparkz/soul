"""Personality drift maintenance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from soul.config import get_settings
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.state.drift import merge_with_baseline, run_weekly_drift


def run_drift_task(
    *,
    resonance_signals: dict[str, float],
    settings=None,
) -> dict[str, object]:
    resolved_settings = settings or get_settings()
    repo = PersonalityStateRepository(resolved_settings.database_url, user_id=resolved_settings.user_id)
    current = merge_with_baseline(repo.get_current_state())
    if not resolved_settings.enable_drift or not resolved_settings.drift_enabled:
        return {"updated": current, "skipped": True}
    updated = run_weekly_drift(current, resonance_signals, settings=resolved_settings)
    record = repo.record_state(updated, resonance_signals=resonance_signals, notes="weekly drift task", source="maintenance")
    return {"updated": updated, "version": record["version"], "skipped": False}


def derive_resonance_signals(database_url: str, *, settings=None) -> dict[str, float]:
    resolved_settings = settings or get_settings()
    messages_repo = MessagesRepository(database_url, user_id=resolved_settings.user_id)
    totals = {
        "humor_intensity": 0.0,
        "response_length": 0.0,
        "curiosity_depth": 0.0,
        "directness": 0.0,
        "warmth_expression": 0.0,
    }
    pair_count = 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=resolved_settings.drift_signal_lookback_days)).isoformat()
    sessions = [s for s in messages_repo.list_sessions(completed_only=True) if str(s.get("started_at", "")) >= cutoff]
    for session in sessions[-resolved_settings.drift_signal_session_limit :]:
        messages = messages_repo.get_session_messages(str(session["id"]))
        for index, message in enumerate(messages[:-1]):
            next_message = messages[index + 1]
            if message["role"] != "assistant" or next_message["role"] != "user":
                continue
            assistant_text = str(message["content"])
            user_text = str(next_message["content"])
            assistant_words = len(assistant_text.split())
            try:
                import json

                metadata = json.loads(str(next_message.get("metadata_json") or "{}"))
            except Exception:
                metadata = {}
            user_words = int(metadata.get("word_count") or len(user_text.split()))
            engagement = min(1.0, user_words / resolved_settings.drift_signal_engagement_divisor)
            if str(next_message.get("user_mood") or "") in {"reflective", "venting", "celebrating"}:
                engagement = min(1.0, engagement + resolved_settings.drift_signal_mood_bonus)
            if engagement <= 0:
                continue

            state = str(message.get("companion_state") or next_message.get("companion_state") or "")
            if assistant_words >= resolved_settings.drift_signal_response_length_min_words:
                totals["response_length"] += engagement
            elif user_words >= resolved_settings.drift_signal_user_depth_min_words:
                totals["response_length"] -= resolved_settings.drift_signal_response_length_penalty

            if "?" in assistant_text or state in {"curious", "reflective"}:
                totals["curiosity_depth"] += engagement
            if state in {"warm", "concerned", "quiet"}:
                totals["warmth_expression"] += engagement
            if state == "playful":
                totals["humor_intensity"] += engagement

            if assistant_words <= resolved_settings.drift_signal_directness_reply_max_words and user_words >= resolved_settings.drift_signal_directness_user_min_words:
                totals["directness"] += resolved_settings.drift_signal_directness_bonus * engagement
            elif assistant_words >= resolved_settings.drift_signal_long_reply_min_words and user_words <= resolved_settings.drift_signal_directness_user_min_words // 2:
                totals["directness"] -= resolved_settings.drift_signal_directness_penalty

            pair_count += 1

    if pair_count == 0:
        return {key: 0.0 for key in totals}
    return {key: round(max(-1.0, min(1.0, value / pair_count)), 4) for key, value in totals.items()}
