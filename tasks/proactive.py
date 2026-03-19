from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

from soul import db
from soul.config import Settings, get_settings
from soul.memory.user_story import UserStory
from soul.memory.user_story import UserStoryRepository
from soul.presence.telegram import TelegramClient
from soul.tasks import celery_app


@dataclass(slots=True)
class ReachOutCandidate:
    trigger: str
    message: str


def load_reach_out_candidates(path: str | Path) -> list[ReachOutCandidate]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    return [ReachOutCandidate(**item) for item in payload]


def save_reach_out_candidates(path: str | Path, candidates: list[ReachOutCandidate]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps([asdict(candidate) for candidate in candidates], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def load_delivery_log(path: str | Path) -> dict[str, object]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_delivery_log(path: str | Path, payload: dict[str, object]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def build_reach_out_candidates(
    *,
    days_since_last_chat: int | None,
    story: UserStory | None = None,
    today: datetime | None = None,
) -> list[ReachOutCandidate]:
    today = today or datetime.now()
    candidates: list[ReachOutCandidate] = []

    if days_since_last_chat is not None and days_since_last_chat >= 3:
        candidates.append(
            ReachOutCandidate(
                trigger="silence_3_days",
                message="It's been a few days. Just checking in. No pressure to perform for me.",
            )
        )

    if today.weekday() == 0:
        candidates.append(
            ReachOutCandidate(
                trigger="monday_morning",
                message="Monday again. How are you walking into the week?",
            )
        )

    if story and story.current_chapter:
        mood = str(story.current_chapter.get("current_mood_trend", "")).casefold()
        if mood in {"stressed", "overwhelmed", "venting"}:
            candidates.append(
                ReachOutCandidate(
                    trigger="past_stress_3d",
                    message="You've seemed under a lot of pressure lately. How is that sitting with you now?",
                )
            )

        summary = str(story.current_chapter.get("summary", ""))
        if "birthday" in summary.casefold():
            candidates.append(
                ReachOutCandidate(
                    trigger="birthday",
                    message="Happy birthday. I hope the day feels like yours.",
                )
            )

    unique: dict[str, ReachOutCandidate] = {}
    for candidate in candidates:
        unique[candidate.trigger] = candidate
    return list(unique.values())


def dispatch_reach_out_candidates(
    settings: Settings,
    candidates: list[ReachOutCandidate],
    *,
    today: datetime | None = None,
) -> dict[str, object]:
    today = today or datetime.now(timezone.utc)
    if not candidates:
        return {"sent": 0, "delivered_triggers": []}
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return {"sent": 0, "delivered_triggers": [], "reason": "telegram not configured"}

    try:
        chat_id = int(settings.telegram_chat_id)
    except ValueError:
        return {"sent": 0, "delivered_triggers": [], "reason": "invalid TELEGRAM_CHAT_ID"}

    delivery_log = load_delivery_log(settings.proactive_delivery_log_file)
    telegram = TelegramClient(settings.telegram_bot_token)
    date_key = today.date().isoformat()
    delivered_triggers: list[str] = []

    for candidate in candidates:
        key = f"{date_key}:{candidate.trigger}"
        if delivery_log.get(key):
            continue
        result = telegram.send_message(chat_id, candidate.message)
        if not result.ok:
            return {"sent": 0, "delivered_triggers": delivered_triggers, "reason": result.error}
        delivery_log[key] = {
            "trigger": candidate.trigger,
            "message": candidate.message,
            "sent_at": today.replace(microsecond=0).isoformat(),
        }
        delivered_triggers.append(candidate.trigger)
        save_delivery_log(settings.proactive_delivery_log_file, delivery_log)
        break

    return {"sent": len(delivered_triggers), "delivered_triggers": delivered_triggers}


if celery_app is not None:

    @celery_app.task(name="soul.tasks.proactive.proactive_presence_task")
    def proactive_presence_task() -> dict[str, object]:
        settings = get_settings()
        db.init_db(settings.database_url)
        story_repo = UserStoryRepository(settings.user_story_file)
        last_message_at = db.get_last_message_timestamp(settings.database_url)
        days_since_last_chat = None
        if last_message_at:
            timestamp = datetime.fromisoformat(last_message_at)
            days_since_last_chat = (datetime.now(timezone.utc) - timestamp).days
        candidates = build_reach_out_candidates(
            days_since_last_chat=days_since_last_chat,
            story=story_repo.load(),
        )
        save_reach_out_candidates(settings.reach_out_candidates_file, candidates)
        delivery = dispatch_reach_out_candidates(settings, candidates)
        return {"candidates": [asdict(item) for item in candidates], "delivery": delivery}
