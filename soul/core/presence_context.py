from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo

from soul import db
from soul.config import Settings
from soul.core.timezone_utils import load_timezone_or_utc


def runtime_timezone(settings: Settings) -> tzinfo:
    return load_timezone_or_utc(settings.timezone_name)


def runtime_now(settings: Settings, *, now: datetime | None = None) -> datetime:
    if now is None:
        base = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        base = now.replace(tzinfo=timezone.utc)
    else:
        base = now.astimezone(timezone.utc)
    return base.astimezone(runtime_timezone(settings))


def _parse_runtime_timestamp(value: str, *, settings: Settings) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(runtime_timezone(settings))


def build_presence_context(
    database_url: str,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build the shared presence context for proactive tasks.

    Args:
        database_url: Database connection URL used to read recent activity.
        settings: Runtime settings object; currently only used to keep the
            helper signature aligned with the single-user/global milestone
            design.

    Returns:
        A dict with `days_since_last_chat`, `stress_signal_dates`, and
        `milestones_today` keys.
    """
    now_local = runtime_now(settings, now=now)
    now_utc = now_local.astimezone(timezone.utc)
    last_message_at = db.get_last_message_timestamp(database_url)
    days_since_last_chat: int | None = None
    if last_message_at:
        timestamp = _parse_runtime_timestamp(last_message_at, settings=settings)
        days_since_last_chat = (now_local - timestamp).days

    stress_events = db.list_user_message_moods_since(
        database_url,
        moods=("stressed", "overwhelmed", "venting"),
        since=(
            now_utc.replace(microsecond=0) - timedelta(days=settings.presence_stress_window_days)
        ).isoformat(),
    )
    stress_signal_dates = [str(item["created_at"]) for item in stress_events]

    milestones_today: list[str] = []
    for milestone in db.list_milestones(database_url, limit=settings.presence_milestone_scan_limit):
        occurred_at = str(milestone.get("occurred_at", ""))
        try:
            occurred = _parse_runtime_timestamp(occurred_at, settings=settings)
        except ValueError:
            continue
        if (occurred.month, occurred.day) == (now_local.month, now_local.day):
            milestones_today.append(str(milestone.get("note") or milestone.get("kind") or "Milestone"))

    first_sessions = db.list_sessions(database_url, limit=1)
    if first_sessions:
        first_started = str(first_sessions[0].get("started_at", ""))
        try:
            first_date = _parse_runtime_timestamp(first_started, settings=settings)
        except ValueError:
            first_date = None
        if (
            first_date
            and first_date.year < now_local.year
            and (first_date.month, first_date.day) == (now_local.month, now_local.day)
        ):
            milestones_today.append("relationship anniversary")

    return {
        "days_since_last_chat": days_since_last_chat,
        "stress_signal_dates": stress_signal_dates,
        "milestones_today": milestones_today,
    }
