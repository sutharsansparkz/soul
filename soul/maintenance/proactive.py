"""Proactive candidate generation and delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from soul.config import Settings, get_settings
from soul.core.presence_context import build_presence_context
from soul.memory.repositories.proactive import ProactiveCandidateRepository
from soul.memory.repositories.user_facts import UserFactsRepository
from soul.presence.telegram import TelegramClient


@dataclass(slots=True)
class ReachOutCandidate:
    trigger: str
    message: str


def build_reach_out_candidates(
    *,
    days_since_last_chat: int | None,
    story=None,
    today: datetime | None = None,
    stress_signal_dates: list[str] | None = None,
    milestones_today: list[str] | None = None,
    settings: Settings | None = None,
) -> list[ReachOutCandidate]:
    resolved_settings = settings or get_settings()
    today = today or datetime.now()
    today_date = today.date()
    candidates: list[ReachOutCandidate] = []

    if days_since_last_chat is not None and days_since_last_chat >= resolved_settings.proactive_silence_days:
        candidates.append(
            ReachOutCandidate(
                trigger=f"silence_{resolved_settings.proactive_silence_days}_days",
                message="It's been a few days. Just checking in. No pressure to perform for me.",
            )
        )

    if today.weekday() == 0:
        candidates.append(ReachOutCandidate(trigger="monday_morning", message="Monday again. How are you walking into the week?"))

    if _has_stress_signal_days_ago(stress_signal_dates or [], today=today_date, days_ago=resolved_settings.proactive_stress_followup_days):
        candidates.append(
            ReachOutCandidate(
                trigger=f"past_stress_{resolved_settings.proactive_stress_followup_days}d",
                message=(
                    f"{resolved_settings.proactive_stress_followup_days} days ago sounded heavy. "
                    "How is that stress sitting with you today?"
                ),
            )
        )

    if story:
        upcoming = _nearest_upcoming_event(story, today=today_date, days_ahead=resolved_settings.proactive_upcoming_event_days)
        if upcoming is not None:
            candidates.append(
                ReachOutCandidate(
                    trigger="upcoming_event",
                    message=f"You have {upcoming['title']} on {upcoming['date']}. Want to check in before it?",
                )
            )

        birthday = _parse_month_day(str(story.basics.get("birthday", "")), fallback_year=today_date.year)
        if birthday and (birthday.month, birthday.day) == (today_date.month, today_date.day):
            candidates.append(ReachOutCandidate(trigger="birthday", message="Happy birthday. I hope the day feels like yours."))

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


def refresh_proactive_candidates(settings: Settings | None = None, *, channel: str = "cli") -> list[ReachOutCandidate]:
    resolved_settings = settings or get_settings()
    story_repo = UserFactsRepository(resolved_settings.database_url, user_id=resolved_settings.user_id)
    presence_context = build_presence_context(resolved_settings.database_url, resolved_settings)
    candidates = build_reach_out_candidates(
        days_since_last_chat=presence_context["days_since_last_chat"],
        story=story_repo.load_story(),
        today=datetime.now(timezone.utc),
        stress_signal_dates=presence_context["stress_signal_dates"],
        milestones_today=presence_context["milestones_today"],
        settings=resolved_settings,
    )
    repo = ProactiveCandidateRepository(resolved_settings.database_url, user_id=resolved_settings.user_id)
    repo.replace_pending(
        [{"trigger": item.trigger, "message": item.message, "status": "pending", "channel": channel} for item in candidates],
        channel=channel,
    )
    return candidates


def dispatch_reach_out_candidates(
    settings: Settings,
    candidates: list[ReachOutCandidate],
    *,
    today: datetime | None = None,
) -> dict[str, object]:
    today = today or datetime.now(timezone.utc)
    if not candidates:
        return {"sent": 0, "delivered_triggers": []}
    if not settings.enable_telegram:
        return {"sent": 0, "delivered_triggers": [], "reason": "telegram feature disabled"}
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return {"sent": 0, "delivered_triggers": [], "reason": "telegram not configured"}

    chat_id = int(settings.telegram_chat_id)
    token = settings.telegram_bot_token.get_secret_value()
    telegram = TelegramClient(
        token,
        base_url=settings.telegram_base_url,
        timeout=settings.telegram_http_timeout,
        longpoll_extra=settings.telegram_longpoll_extra_seconds,
        poll_timeout=settings.telegram_poll_timeout,
    )
    repo = ProactiveCandidateRepository(settings.database_url, user_id=settings.user_id)
    delivered_triggers: list[str] = []
    recent = repo.list(channel="telegram", limit=50)
    delivered_today = {
        str(item.get("trigger"))
        for item in recent
        if str(item.get("status")) == "delivered" and str(item.get("delivered_at", ""))[:10] == today.date().isoformat()
    }

    for candidate in candidates:
        if candidate.trigger in delivered_today:
            continue
        result = telegram.send_message(chat_id, candidate.message)
        if not result.ok:
            return {"sent": 0, "delivered_triggers": delivered_triggers, "reason": result.error}
        repo.replace_pending(
            [
                {
                    "trigger": candidate.trigger,
                    "message": candidate.message,
                    "status": "delivered",
                    "channel": "telegram",
                    "delivered_at": today.replace(microsecond=0).isoformat(),
                }
            ],
            channel="telegram",
        )
        delivered_triggers.append(candidate.trigger)
        break
    return {"sent": len(delivered_triggers), "delivered_triggers": delivered_triggers}


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
        return date(fallback_year, month, day)
    except ValueError:
        return None


def _has_stress_signal_days_ago(values: list[str], *, today: date, days_ago: int) -> bool:
    target = today - timedelta(days=days_ago)
    for item in values:
        try:
            observed = datetime.fromisoformat(item).date()
        except ValueError:
            continue
        if observed == target:
            return True
    return False


def _nearest_upcoming_event(story, *, today: date, days_ahead: int) -> dict[str, str] | None:  # type: ignore[no-untyped-def]
    nearest: tuple[date, dict[str, str]] | None = None
    for event in getattr(story, "upcoming_events", []) or []:
        if not isinstance(event, dict):
            continue
        raw_date = str(event.get("date", "")).strip()
        raw_title = str(event.get("title", "")).strip() or "something important"
        try:
            event_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        days_until = (event_date - today).days
        if days_until < 0 or days_until > days_ahead:
            continue
        normalized = {"date": raw_date, "title": raw_title[:100]}
        if nearest is None or event_date < nearest[0]:
            nearest = (event_date, normalized)
    return nearest[1] if nearest else None
