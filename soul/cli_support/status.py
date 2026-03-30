from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Callable

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from soul import db
from soul import __version__
from soul.config import Settings, get_settings
from soul.core.mood_engine import MoodEngine
from soul.core.presence_context import build_presence_context, runtime_now
from soul.core.soul_loader import Soul
from soul.maintenance.jobs import run_enabled_maintenance
from soul.maintenance.proactive import refresh_proactive_candidates
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.presence.telegram import TelegramBotRunner
from soul.presence.voice import VoiceBridge


def parse_iso_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_countdown(count: int, singular: str, plural: str | None = None) -> str:
    plural = plural or f"{singular}s"
    unit = singular if count == 1 else plural
    return f"{count} {unit} away"


def message_milestone_label(count: int) -> str:
    if count == 100:
        return "100th message"
    return f"{count}-message milestone"


def conversation_streak_progress(settings: Settings, *, now: datetime) -> int:
    session_days = sorted(
        {
            parse_iso_datetime(str(session["started_at"])).astimezone(now.tzinfo).date()
            for session in db.list_sessions(settings.database_url)
            if session.get("started_at")
        }
    )
    if not session_days:
        return 0

    latest_day = session_days[-1]
    if latest_day < now.date() - timedelta(days=1):
        return 0

    streak = 1
    for index in range(len(session_days) - 1, 0, -1):
        current = session_days[index]
        previous = session_days[index - 1]
        if (current - previous) == timedelta(days=1):
            streak += 1
            continue
        break
    return streak


def anniversary_progress(settings: Settings, *, days: int, now: datetime) -> int | None:
    sessions = db.list_sessions(settings.database_url, limit=1)
    if not sessions:
        return None
    first_date = parse_iso_datetime(str(sessions[0]["started_at"])).astimezone(now.tzinfo).date()
    elapsed = (now.date() - first_date).days
    return max(0, days - elapsed)


def next_milestone_label(
    settings: Settings,
    total_messages: int,
    *,
    now: datetime | None = None,
    runtime_now_func: Callable[..., datetime] = runtime_now,
) -> str:
    now = now or runtime_now_func(settings)
    candidates: list[tuple[int, str, str]] = []

    if total_messages < settings.milestone_message_count and not db.milestone_exists(settings.database_url, "hundredth_message"):
        remaining = max(0, settings.milestone_message_count - total_messages)
        candidates.append(
            (
                3 if remaining > 0 else 0,
                "hundredth_message",
                f"{message_milestone_label(settings.milestone_message_count)} ({remaining} away)",
            )
        )

    if not db.milestone_exists(settings.database_url, "seven_day_streak"):
        streak = conversation_streak_progress(settings, now=now)
        remaining = max(0, settings.milestone_streak_days - streak) if streak else settings.milestone_streak_days
        label = (
            f"{settings.milestone_streak_days}-day conversation streak (today)"
            if remaining == 0
            else f"{settings.milestone_streak_days}-day conversation streak ({format_countdown(remaining, 'day')})"
        )
        candidates.append((remaining, "seven_day_streak", label))

    if not db.milestone_exists(settings.database_url, "one_month_anniversary"):
        remaining = anniversary_progress(settings, days=settings.milestone_one_month_days, now=now)
        if remaining is not None:
            label = "1-month anniversary (today)" if remaining == 0 else f"1-month anniversary ({format_countdown(remaining, 'day')})"
            candidates.append((remaining, "one_month_anniversary", label))

    if not db.milestone_exists(settings.database_url, "three_month_anniversary"):
        remaining = anniversary_progress(settings, days=settings.milestone_three_month_days, now=now)
        if remaining is not None:
            label = "3-month anniversary (today)" if remaining == 0 else f"3-month anniversary ({format_countdown(remaining, 'day')})"
            candidates.append((remaining, "three_month_anniversary", label))

    if not candidates:
        return "relationship timeline is active"

    _, _, label = min(candidates, key=lambda item: (item[0], item[1]))
    return label


def render_drift(console: Console, settings: Settings) -> None:
    runs = PersonalityStateRepository(settings.database_url, user_id=settings.user_id).list_history(limit=21)
    if not runs:
        console.print("[dim]No drift runs recorded yet.[/dim]")
        return
    runs_asc = list(reversed(runs))
    table = Table(title="Drift History", box=box.SIMPLE_HEAVY)
    table.add_column("Date", style="cyan", width=14)
    table.add_column("State", style="white")
    table.add_column("Signals", style="dim")
    for row in runs_asc[-20:]:
        state_raw = row.get("state_json", "{}")
        signals_raw = row.get("resonance_signals_json", "{}")
        try:
            state_dict = json.loads(str(state_raw)) if isinstance(state_raw, str) else state_raw
            state_str = "  ".join(f"{k}: {v:.3f}" for k, v in state_dict.items()) if state_dict else "{}"
        except (json.JSONDecodeError, TypeError, AttributeError):
            state_str = str(state_raw)
        try:
            sig_dict = json.loads(str(signals_raw)) if isinstance(signals_raw, str) else signals_raw
            sig_str = "  ".join(f"{k}: {v:+.3f}" for k, v in sig_dict.items()) if sig_dict else "{}"
        except (json.JSONDecodeError, TypeError, AttributeError):
            sig_str = str(signals_raw)
        table.add_row(str(row.get("created_at", ""))[:10], state_str, sig_str)
    console.print(table)


def render_milestones(console: Console, settings: Settings, *, relative_time_func: Callable[[str], str]) -> None:
    rows = db.list_milestones(settings.database_url)
    if not rows:
        console.print("[dim]No milestones recorded yet.[/dim]")
        return
    table = Table(title="Relationship Timeline", box=box.SIMPLE_HEAVY)
    table.add_column("When", style="cyan", width=16)
    table.add_column("Kind", style="magenta", width=24)
    table.add_column("Note", style="white")
    for row in rows:
        table.add_row(relative_time_func(str(row["occurred_at"])), str(row["kind"]), str(row["note"]))
    console.print(table)


def render_status(
    console: Console,
    settings: Settings,
    soul: Soul,
    *,
    next_milestone_label_func: Callable[..., str],
    runtime_now_func: Callable[..., datetime] = runtime_now,
    refresh_proactive_candidates_func=refresh_proactive_candidates,
) -> None:
    mood_engine = MoodEngine(settings)
    voice_bridge = VoiceBridge(settings) if settings.enable_voice else None
    telegram_runner = TelegramBotRunner(settings=settings) if settings.enable_telegram else None
    now = runtime_now_func(settings)
    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)
    total_sessions = messages_repo.count_sessions()
    total_messages = messages_repo.count_messages(role="user")
    presence_context = build_presence_context(settings.database_url, settings, now=now)
    queued_candidates = refresh_proactive_candidates_func(settings, channel="cli") if settings.enable_proactive else []

    current_state = mood_engine.current_state(settings.user_id) or {}
    mood_state = current_state.get("state") or db.get_last_companion_state(settings.database_url) or "no sessions yet"
    table = Table(title="SOUL Status", box=box.SIMPLE_HEAVY)
    table.add_column("Field", style="magenta", width=22)
    table.add_column("Value", style="white")
    table.add_row("Companion", soul.name)
    table.add_row("Database", settings.redacted_database_url)
    table.add_row("Environment", settings.environment)
    table.add_row("Chat sessions", str(total_sessions))
    table.add_row("Your messages", str(total_messages))
    table.add_row(
        "Days since last chat",
        "never" if presence_context["days_since_last_chat"] is None else str(presence_context["days_since_last_chat"]),
    )
    table.add_row("Companion mood", str(mood_state))
    table.add_row("Reach-out candidates", str(len(queued_candidates)))
    table.add_row("Voice", voice_bridge.status()["voice"] if voice_bridge else "disabled by feature flag")
    table.add_row("Telegram", telegram_runner.status()["telegram"] if telegram_runner else "disabled by feature flag")
    table.add_row("Next milestone", next_milestone_label_func(settings, total_messages, now=now))
    console.print(table)


def run_jobs(console: Console, settings: Settings, *, run_enabled_maintenance_func=run_enabled_maintenance) -> None:
    try:
        results = run_enabled_maintenance_func(settings)
    except Exception as exc:
        console.print(f"[red]Maintenance run failed.[/red] {exc}")
        raise typer.Exit(code=1)
    table = Table(title="Maintenance Results", box=box.SIMPLE_HEAVY)
    table.add_column("Job", style="cyan")
    table.add_column("Result", style="white")
    if isinstance(results, dict):
        for job, result in results.items():
            table.add_row(str(job), str(result))
    else:
        table.add_row("output", str(results))
    console.print(table)
    console.print("[green]Maintenance run completed.[/green]")


def run_telegram_bot(console: Console, *, settings_loader=get_settings, telegram_runner_cls=TelegramBotRunner) -> None:
    settings = settings_loader()
    if not settings.enable_telegram:
        console.print("[yellow]Telegram feature is disabled. Set ENABLE_TELEGRAM=true to use this command.[/yellow]")
        raise typer.Exit(code=1)
    runner = telegram_runner_cls(settings=settings_loader())
    status_map = runner.status()
    table = Table(title="SOUL Telegram Bot", box=box.SIMPLE_HEAVY)
    table.add_column("Component", style="magenta")
    table.add_column("State", style="white")
    for key, value in status_map.items():
        table.add_row(key, value)
    console.print(table)
    if status_map["telegram"].startswith("disabled"):
        raise typer.Exit(code=0)
    try:
        runner.run_forever()
    except Exception as exc:
        console.print(f"[red]Telegram bot stopped.[/red] {exc}")
        raise typer.Exit(code=1)


def render_config(console: Console) -> None:
    settings = get_settings()
    console.print_json(json.dumps(settings.as_redacted_dict(), indent=2))


def render_version(console: Console) -> None:
    console.print(f"SOUL {__version__}")
