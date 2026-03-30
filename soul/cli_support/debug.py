from __future__ import annotations

import json

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from soul.config import Settings
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.mood import MoodSnapshotsRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.memory.repositories.user_facts import UserFactsRepository
from soul.observability.traces import TurnTraceRepository


def render_last_turn(console: Console, settings: Settings) -> None:
    trace = TurnTraceRepository(settings.database_url, user_id=settings.user_id).get_last_trace()
    if trace is None:
        console.print("[dim]No turn traces recorded yet.[/dim]")
        return
    console.print_json(json.dumps(trace, indent=2, ensure_ascii=True))


def render_mood(console: Console, settings: Settings) -> None:
    payload = MoodSnapshotsRepository(settings.database_url, user_id=settings.user_id).latest()
    if payload is None:
        console.print("[dim]No mood snapshots recorded yet.[/dim]")
        return
    table = Table(title="Latest Mood Snapshot", box=box.SIMPLE_HEAVY, show_header=False)
    table.add_column("Field", style="magenta", width=20)
    table.add_column("Value", style="white")
    for key in ("user_mood", "companion_state", "confidence", "rationale", "created_at"):
        if key in payload:
            table.add_row(key.replace("_", " ").title(), str(payload[key]))
    console.print(table)


def render_facts(console: Console, settings: Settings) -> None:
    payload = UserFactsRepository(settings.database_url, user_id=settings.user_id).export_story_payload()
    console.print_json(json.dumps(payload, indent=2, ensure_ascii=True))


def render_memories(console: Console, settings: Settings, *, limit: int) -> None:
    records = EpisodicMemoryRepository(settings=settings).list_top(limit=limit)
    if not records:
        console.print("[dim]No memories stored yet.[/dim]")
        return
    table = Table(title=f"Episodic Memories (top {limit})", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=7)
    table.add_column("Tier", style="magenta", width=9)
    table.add_column("Tag", style="dim", width=12)
    table.add_column("Source", style="dim", width=18)
    table.add_column("Date", style="dim", width=12)
    table.add_column("Content", style="white")
    for record in records:
        ts = str(record.metadata.get("timestamp", ""))[:10]
        table.add_row(
            f"{float(record.metadata.get('hms_score', 0)):.2f}",
            str(record.metadata.get("tier", "")),
            str(record.emotional_tag or ""),
            str(record.metadata.get("source", "")),
            ts,
            str(record.content),
        )
    console.print(table)


def render_personality(console: Console, settings: Settings, *, limit: int) -> None:
    rows = PersonalityStateRepository(settings.database_url, user_id=settings.user_id).list_history(limit=limit)
    if not rows:
        console.print("[dim]No personality state recorded yet.[/dim]")
        return
    table = Table(title="Personality State History", box=box.SIMPLE_HEAVY)
    table.add_column("Ver", style="cyan", width=5)
    table.add_column("Date", style="dim", width=12)
    table.add_column("State", style="white")
    table.add_column("Signals", style="dim")
    for row in rows:
        try:
            state_dict = json.loads(str(row.get("state_json", "{}")))
            state_str = "  ".join(f"{k}: {v:.3f}" for k, v in state_dict.items())
        except (json.JSONDecodeError, TypeError):
            state_str = str(row.get("state_json", ""))
        try:
            sig_dict = json.loads(str(row.get("resonance_signals_json", "{}")))
            sig_str = "  ".join(f"{k}: {v:+.3f}" for k, v in sig_dict.items())
        except (json.JSONDecodeError, TypeError):
            sig_str = str(row.get("resonance_signals_json", ""))
        table.add_row(str(row.get("version", "")), str(row.get("created_at", ""))[:10], state_str, sig_str)
    console.print(table)


def render_trace(console: Console, settings: Settings, trace_id: str) -> None:
    trace = TurnTraceRepository(settings.database_url).get_trace(trace_id)
    if trace is None:
        console.print(f"[red]Trace not found:[/red] {trace_id}")
        raise typer.Exit(code=1)
    console.print_json(json.dumps(trace, indent=2, ensure_ascii=True))


def render_memory_row(console: Console, settings: Settings, memory_id: str) -> None:
    row = EpisodicMemoryRepository(settings=settings).get_row(memory_id)
    if row is None:
        console.print(f"[red]Memory not found:[/red] {memory_id}")
        raise typer.Exit(code=1)
    console.print_json(json.dumps(row, indent=2, ensure_ascii=True))

