from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json

from soul import db
from soul.config import Settings, get_settings
from soul.core.presence_context import build_presence_context
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
    try:
        file_path.chmod(0o600)
    except OSError:
        pass


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
    try:
        file_path.chmod(0o600)
    except OSError:
        pass


def build_reach_out_candidates(
    *,
    days_since_last_chat: int | None,
    story: UserStory | None = None,
    today: datetime | None = None,
    stress_signal_dates: list[str] | None = None,
    milestones_today: list[str] | None = None,
) -> list[ReachOutCandidate]:
    today = today or datetime.now()
    today_date = today.date()
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

    if _has_stress_signal_three_days_ago(stress_signal_dates or [], today=today_date):
        candidates.append(
            ReachOutCandidate(
                trigger="past_stress_3d",
                message="Three days ago sounded heavy. How is that stress sitting with you today?",
            )
        )

    if story:
        upcoming = _nearest_upcoming_event(story, today=today_date)
        if upcoming is not None:
            candidates.append(
                ReachOutCandidate(
                    trigger="upcoming_event",
                    message=f"You have {upcoming['title']} on {upcoming['date']}. Want to check in before it?",
                )
            )

        birthday = _parse_month_day(str(story.basics.get("birthday", "")), fallback_year=today_date.year)
        if birthday and (birthday.month, birthday.day) == (today_date.month, today_date.day):
            candidates.append(
                ReachOutCandidate(
                    trigger="birthday",
                    message="Happy birthday. I hope the day feels like yours.",
                )
            )

    if milestones_today:
        milestone_label = milestones_today[0]
        candidates.append(
            ReachOutCandidate(
                trigger="milestone_today",
                message=f"It's a milestone day: {milestone_label}. I'm glad we've made it here together.",
            )
        )

    unique: dict[str, ReachOutCandidate] = {}
    for candidate in candidates:
        unique[candidate.trigger] = candidate
    return list(unique.values())


def _parse_month_day(value: str, *, fallback_year: int) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass
    parts = text.split("-")
    if len(parts) != 2:
        return None
    try:
        month, day = (int(part) for part in parts)
    except ValueError:
        return None
    try:
        return date(fallback_year, month, day)
    except ValueError:
        try:
            return date(2000, month, day)
        except ValueError:
            return None


def _has_stress_signal_three_days_ago(values: list[str], *, today: date) -> bool:
    target = today - timedelta(days=3)
    for item in values:
        try:
            observed = datetime.fromisoformat(item).date()
        except ValueError:
            continue
        if observed == target:
            return True
    return False


def _nearest_upcoming_event(story: UserStory, *, today: date) -> dict[str, str] | None:
    events = getattr(story, "upcoming_events", []) or []
    nearest: tuple[date, dict[str, str]] | None = None
    for event in events:
        if not isinstance(event, dict):
            continue
        raw_date = str(event.get("date", "")).strip()
        raw_title = str(event.get("title", "")).strip() or "something important"
        try:
            event_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        days_until = (event_date - today).days
        if days_until < 0 or days_until > 7:
            continue
        normalized = {"date": raw_date, "title": raw_title[:100]}
        if nearest is None or event_date < nearest[0]:
            nearest = (event_date, normalized)
    return nearest[1] if nearest else None


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
    token = settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else None
    telegram = TelegramClient(token)
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
        presence_context = build_presence_context(settings.database_url, settings)
        now = datetime.now(timezone.utc)
        candidates = build_reach_out_candidates(
            days_since_last_chat=presence_context["days_since_last_chat"],
            story=story_repo.load(),
            today=now,
            stress_signal_dates=presence_context["stress_signal_dates"],
            milestones_today=presence_context["milestones_today"],
        )
        save_reach_out_candidates(settings.reach_out_candidates_file, candidates)
        delivery = dispatch_reach_out_candidates(settings, candidates)
        return {"candidates": [asdict(item) for item in candidates], "delivery": delivery}
