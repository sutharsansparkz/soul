from __future__ import annotations

from datetime import datetime, timedelta, timezone

from soul import db
from soul.config import Settings


def build_presence_context(database_url: str, settings: Settings) -> dict[str, object]:
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
    # Current milestone and presence context is global in this single-user design.
    _ = settings
    now = datetime.now(timezone.utc)
    last_message_at = db.get_last_message_timestamp(database_url)
    days_since_last_chat: int | None = None
    if last_message_at:
        timestamp = datetime.fromisoformat(last_message_at)
        days_since_last_chat = (now - timestamp).days

    stress_events = db.list_user_message_moods_since(
        database_url,
        moods=("stressed", "overwhelmed", "venting"),
        since=(now.replace(microsecond=0) - timedelta(days=14)).isoformat(),
    )
    stress_signal_dates = [str(item["created_at"]) for item in stress_events]

    milestones_today: list[str] = []
    for milestone in db.list_milestones(database_url, limit=200):
        occurred_at = str(milestone.get("occurred_at", ""))
        try:
            occurred = datetime.fromisoformat(occurred_at)
        except ValueError:
            continue
        if (occurred.month, occurred.day) == (now.month, now.day):
            milestones_today.append(str(milestone.get("note") or milestone.get("kind") or "Milestone"))

    first_sessions = db.list_sessions(database_url, limit=1)
    if first_sessions:
        first_started = str(first_sessions[0].get("started_at", ""))
        try:
            first_date = datetime.fromisoformat(first_started)
        except ValueError:
            first_date = None
        if first_date and first_date.year < now.year and (first_date.month, first_date.day) == (now.month, now.day):
            milestones_today.append("relationship anniversary")

    return {
        "days_since_last_chat": days_since_last_chat,
        "stress_signal_dates": stress_signal_dates,
        "milestones_today": milestones_today,
    }
