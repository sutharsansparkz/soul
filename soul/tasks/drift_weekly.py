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


def run_drift_task(personality_path: str | Path, log_path: str | Path, resonance_signals: dict[str, float]) -> DriftTaskResult:
    personality_file = Path(personality_path)
    current = json.loads(personality_file.read_text(encoding="utf-8")) if personality_file.exists() else {}
    current = merge_with_baseline(current)
    updated = run_weekly_drift(current, resonance_signals)
    personality_file.parent.mkdir(parents=True, exist_ok=True)
    personality_file.write_text(json.dumps(updated, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    repo = DriftLogRepository(log_path)
    runs = repo.load()
    runs.append(
        DriftRun(
            run_date=datetime.now(timezone.utc).date().isoformat(),
            dimensions_before=current,
            dimensions_after=updated,
            resonance_signals=resonance_signals,
            notes="weekly drift task",
        )
    )
    repo.save(runs)
    return DriftTaskResult(updated=updated, log_path=str(Path(log_path)))


def derive_resonance_signals(database_url: str) -> dict[str, float]:
    totals = {
        "humor_intensity": 0.0,
        "response_length": 0.0,
        "curiosity_depth": 0.0,
        "directness": 0.0,
        "warmth_expression": 0.0,
    }
    pair_count = 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    sessions = [s for s in db.list_sessions(database_url, completed_only=True) if str(s.get("started_at", "")) >= cutoff]
    for session in sessions[-50:]:
        messages = db.get_session_messages(database_url, str(session["id"]))
        for index, message in enumerate(messages[:-1]):
            next_message = messages[index + 1]
            if message["role"] != "assistant" or next_message["role"] != "user":
                continue
            assistant_text = str(message["content"])
            user_text = str(next_message["content"])
            assistant_words = len(assistant_text.split())
            user_words = len(user_text.split())
            engagement = min(1.0, user_words / 35.0)
            if str(next_message.get("user_mood") or "") in {"reflective", "venting", "celebrating"}:
                engagement += 0.15
            if engagement <= 0:
                continue

            state = str(message.get("companion_state") or next_message.get("companion_state") or "")
            if assistant_words >= 35:
                totals["response_length"] += engagement
            elif user_words >= 20:
                totals["response_length"] -= 0.1

            if "?" in assistant_text or state in {"curious", "reflective"}:
                totals["curiosity_depth"] += engagement
            if state in {"warm", "concerned", "quiet"}:
                totals["warmth_expression"] += engagement
            if state == "playful":
                totals["humor_intensity"] += engagement

            if assistant_words <= 30 and user_words >= 15:
                totals["directness"] += 0.4 * engagement
            elif assistant_words >= 60 and user_words <= 8:
                totals["directness"] -= 0.2

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
        signals = derive_resonance_signals(settings.database_url)
        result = run_drift_task(settings.personality_file, settings.drift_log_file, signals)
        return {"updated": result.updated, "log_path": result.log_path}
