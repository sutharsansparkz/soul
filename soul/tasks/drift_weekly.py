from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from soul import db
from soul.config import get_settings
from soul.evolution.drift_engine import DriftLogRepository, DriftRun, merge_with_baseline, run_weekly_drift
from soul.tasks import celery_app


@dataclass(slots=True)
class DriftTaskResult:
    updated: dict[str, float]
    log_path: str


def run_drift_task(
    personality_path: str | Path,
    log_path: str | Path,
    resonance_signals: dict[str, float],
    *,
    settings=None,
) -> DriftTaskResult:
    resolved_settings = settings or get_settings()
    personality_file = Path(personality_path)
    current = json.loads(personality_file.read_text(encoding="utf-8")) if personality_file.exists() else {}
    current = merge_with_baseline(current)
    if not resolved_settings.drift_enabled:
        return DriftTaskResult(updated=current, log_path=str(Path(log_path)))
    updated = run_weekly_drift(current, resonance_signals, settings=resolved_settings)
    run_date = datetime.now(timezone.utc).date().isoformat()
    personality_file.parent.mkdir(parents=True, exist_ok=True)
    personality_file.write_text(json.dumps(updated, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    repo = DriftLogRepository(log_path)
    runs = repo.load()
    runs.append(
        DriftRun(
            run_date=run_date,
            dimensions_before=current,
            dimensions_after=updated,
            resonance_signals=resonance_signals,
            notes="weekly drift task",
        )
    )
    repo.save(runs)
    if resolved_settings.database_url:
        try:
            db.insert_drift_log(
                resolved_settings.database_url,
                run_date=runs[-1].run_date,
                dimensions_before=runs[-1].dimensions_before,
                dimensions_after=runs[-1].dimensions_after,
                resonance_signals=runs[-1].resonance_signals,
                notes=runs[-1].notes,
            )
        except Exception:
            pass
    return DriftTaskResult(updated=updated, log_path=str(Path(log_path)))


def derive_resonance_signals(database_url: str, *, settings=None) -> dict[str, float]:
    resolved_settings = settings or get_settings()
    totals = {
        "humor_intensity": 0.0,
        "response_length": 0.0,
        "curiosity_depth": 0.0,
        "directness": 0.0,
        "warmth_expression": 0.0,
    }
    pair_count = 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=resolved_settings.drift_signal_lookback_days)).isoformat()
    sessions = [s for s in db.list_sessions(database_url, completed_only=True) if str(s.get("started_at", "")) >= cutoff]
    for session in sessions[-resolved_settings.drift_signal_session_limit :]:
        messages = db.get_session_messages(database_url, str(session["id"]))
        for index, message in enumerate(messages[:-1]):
            next_message = messages[index + 1]
            if message["role"] != "assistant" or next_message["role"] != "user":
                continue
            assistant_text = str(message["content"])
            user_text = str(next_message["content"])
            assistant_words = len(assistant_text.split())
            metadata: dict[str, object]
            try:
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

            if (
                assistant_words <= resolved_settings.drift_signal_directness_reply_max_words
                and user_words >= resolved_settings.drift_signal_directness_user_min_words
            ):
                totals["directness"] += resolved_settings.drift_signal_directness_bonus * engagement
            elif (
                assistant_words >= resolved_settings.drift_signal_long_reply_min_words
                and user_words <= resolved_settings.drift_signal_directness_user_min_words // 2
            ):
                totals["directness"] -= resolved_settings.drift_signal_directness_penalty

            pair_count += 1

    if pair_count == 0:
        return {key: 0.0 for key in totals}

    normalized = {}
    for key, value in totals.items():
        normalized[key] = round(max(-1.0, min(1.0, value / pair_count)), 4)
    return normalized


if celery_app is not None:

    @celery_app.task(name="soul.tasks.drift_weekly.weekly_drift_task")
    def weekly_drift_task() -> dict[str, object]:
        settings = get_settings()
        db.init_db(settings.database_url)
        if not settings.drift_enabled:
            current = json.loads(settings.personality_file.read_text(encoding="utf-8")) if settings.personality_file.exists() else {}
            return {"updated": merge_with_baseline(current), "log_path": str(settings.drift_log_file), "skipped": True}
        signals = derive_resonance_signals(settings.database_url, settings=settings)
        result = run_drift_task(settings.personality_file, settings.drift_log_file, signals, settings=settings)
        return {"updated": result.updated, "log_path": result.log_path, "skipped": False}
