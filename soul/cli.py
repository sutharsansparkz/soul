from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from soul import __version__, db
from soul.config import Settings, get_settings
from soul.core.context_builder import ContextBuilder
from soul.core.llm_client import LLMClient, LLMResult
from soul.core.mood_engine import MoodEngine, MoodSnapshot
from soul.core.post_processor import PostProcessor
from soul.core.soul_loader import Soul, load_soul
from soul.evolution.drift_engine import DriftLogRepository
from soul.evolution.reflection import generate_monthly_reflection
from soul.memory.episodic import EpisodicMemoryRepository
from soul.presence.telegram import TelegramBotRunner
from soul.presence.voice import VoiceBridge
from soul.memory.user_story import UserStoryRepository
from soul.tasks.consolidate import archive_and_purge_old_session_messages, consolidate_pending_sessions
from soul.tasks.drift_weekly import derive_resonance_signals, run_drift_task
from soul.tasks.hms_decay import run_hms_decay
from soul.tasks.proactive import (
    build_reach_out_candidates,
    dispatch_reach_out_candidates,
    load_reach_out_candidates,
    save_reach_out_candidates,
)


app = typer.Typer(help="SOUL, an AI companion from your terminal.", add_completion=False)
memories_app = typer.Typer(help="Memory commands.", invoke_without_command=True, no_args_is_help=False)
story_app = typer.Typer(help="User story commands.", invoke_without_command=True, no_args_is_help=False)
db_app = typer.Typer(help="Database commands.", invoke_without_command=True, no_args_is_help=False)
app.add_typer(memories_app, name="memories")
app.add_typer(story_app, name="story")
app.add_typer(db_app, name="db")

console = Console()


def _bootstrap() -> tuple[Settings, Soul]:
    settings = get_settings()
    _ensure_runtime_files(settings)
    db.init_db(settings.database_url)
    soul = load_soul(settings.soul_file)
    return settings, soul


def _ensure_runtime_files(settings: Settings) -> None:
    settings.soul_data_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_is_sqlite:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    settings.session_log_dir.mkdir(parents=True, exist_ok=True)
    settings.session_archive_dir.mkdir(parents=True, exist_ok=True)

    for path, default in (
        (settings.reach_out_candidates_file, "[]\n"),
        (settings.shared_language_file, "[]\n"),
        (settings.drift_log_file, "[]\n"),
        (settings.consolidation_ledger_file, "{}\n"),
        (settings.proactive_delivery_log_file, "{}\n"),
        (settings.episodic_memory_file, ""),
        (settings.reflections_file, "[]\n"),
        (settings.milestones_file, "[]\n"),
    ):
        if not path.exists():
            path.write_text(default, encoding="utf-8")


def _print_header(soul: Soul, session_id: str, mood: MoodSnapshot | None = None) -> None:
    status = f"{soul.name} - session {session_id[:8]} - /quit to exit"
    if mood:
        status = f"{status} - mood: {mood.companion_state}"
    console.print()
    console.print(Panel(status, box=box.SIMPLE, border_style="magenta"))


def _render_live_reply(
    client: LLMClient,
    *,
    speaker_name: str,
    system_prompt: str,
    messages: list[dict[str, str]],
    mood: MoodSnapshot,
) -> LLMResult:
    live_text = Text("", style="white")
    panel = Panel(live_text, box=box.SIMPLE, border_style="cyan", title=speaker_name)

    def handle_chunk(chunk: str) -> None:
        if not chunk:
            return
        live_text.append(chunk)
        live.update(Panel(live_text, box=box.SIMPLE, border_style="cyan", title=speaker_name))

    with Live(panel, console=console, refresh_per_second=25, transient=True) as live:
        result = client.reply(
            system_prompt=system_prompt,
            messages=messages,
            mood=mood,
            stream_handler=handle_chunk,
        )
    console.print(f"[bold magenta]{speaker_name}[/bold magenta] > {result.text}")
    return result


def _show_last_session(settings: Settings) -> None:
    session_id = db.get_last_completed_session_id(settings.database_url)
    if not session_id:
        console.print("[dim]No previous session found.[/dim]")
        return

    rows = db.get_session_messages(settings.database_url, session_id)
    table = Table(title="Last Session Replay", box=box.SIMPLE_HEAVY)
    table.add_column("Role", style="cyan", width=10)
    table.add_column("Message", style="white")
    for row in rows[-8:]:
        table.add_row(str(row["role"]), str(row["content"]))
    console.print(table)


def _render_story(path: Path) -> None:
    if not path.exists():
        console.print("[dim]No user story exists yet.[/dim]")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    console.print_json(json.dumps(payload))


def _export_latest_session_log(settings: Settings) -> Path:
    last_session_id = db.get_last_completed_session_id(settings.database_url)
    session_log = settings.latest_session_log_file
    if not last_session_id:
        return session_log
    lines = [f"{row['role']}: {row['content']}" for row in db.get_session_messages(settings.database_url, last_session_id)]
    session_log.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return session_log


def _voice_output(voice_bridge: VoiceBridge, enabled: bool, text: str) -> None:
    if not enabled:
        return
    result = voice_bridge.speak(text)
    if result.ok:
        console.print(f"[dim]voice output saved to {result.output_path}[/dim]")
    else:
        console.print(f"[yellow]voice output skipped: {result.error}[/yellow]")


def _normalize_voice_transcript(text: str) -> str:
    normalized = text.strip()
    lowered = normalized.casefold()
    if lowered in {"quit", "exit", "goodbye", "stop"}:
        return "/quit"
    if lowered in {"show mood", "what is my mood"}:
        return "/mood"
    return normalized


def _capture_voice_input(voice_bridge: VoiceBridge, *, seconds: int) -> str | None:
    recording = voice_bridge.record_to_file(seconds=seconds)
    if not recording.ok or not recording.output_path:
        console.print(f"[yellow]voice recording unavailable: {recording.error}[/yellow]")
        return None

    transcript = voice_bridge.transcribe(recording.output_path)
    if not transcript.ok or not transcript.text:
        console.print(f"[yellow]voice transcription unavailable: {transcript.error}[/yellow]")
        return None

    console.print(f"[dim]recorded and transcribed voice input from {recording.output_path}[/dim]")
    return _normalize_voice_transcript(transcript.text)


def _handle_session_command(
    raw_input: str,
    *,
    settings: Settings,
    session_id: str,
    current_mood: MoodSnapshot | None,
    voice_enabled: bool,
    episodic_repo: EpisodicMemoryRepository,
) -> tuple[bool, bool]:
    parts = shlex.split(raw_input)
    command = parts[0].casefold()

    if command == "/quit":
        console.print("\n[dim]See you next time.[/dim]")
        return True, voice_enabled

    if command == "/mood":
        if current_mood is None:
            console.print("[dim]No mood has been detected yet in this session.[/dim]")
        else:
            console.print(
                f"[cyan]user_mood[/cyan]={current_mood.user_mood}  "
                f"[magenta]companion_state[/magenta]={current_mood.companion_state}  "
                f"[dim]{current_mood.rationale}[/dim]"
            )
        return False, voice_enabled

    if command == "/story":
        _render_story(settings.user_story_file)
        return False, voice_enabled

    if command == "/save":
        note = " ".join(parts[1:]).strip()
        if not note:
            console.print("[red]Usage:[/red] /save \"note text\"")
            return False, voice_enabled
        emotional_tag = current_mood.user_mood if current_mood is not None else None
        saved = episodic_repo.add_text(
            note,
            emotional_tag=emotional_tag,
            importance=0.9,
            memory_type="insight",
            metadata={
                "session_id": session_id,
                "user_id": settings.user_id,
                "flagged": True,
                "timestamp": db.utcnow_iso(),
                "source": "manual_save",
            },
        )
        db.save_memory(settings.database_url, label="manual note", content=note, session_id=session_id, importance=0.9)
        score = float(saved.metadata.get("hms_score", 0.5))
        console.print(f"[green]Saved and boosted memory.[/green] HMS={score:.2f}")
        return False, voice_enabled

    if command == "/voice":
        requested = parts[1].casefold() if len(parts) > 1 else ""
        if requested not in {"on", "off"}:
            console.print("[red]Usage:[/red] /voice on|off")
            return False, voice_enabled
        voice_enabled = requested == "on"
        console.print(f"[green]Voice output {'enabled' if voice_enabled else 'disabled'} for this session.[/green]")
        return False, voice_enabled

    console.print(f"[red]Unknown command:[/red] {command}")
    return False, voice_enabled


@app.command()
def chat(
    voice: bool = typer.Option(False, "--voice", help="Synthesize assistant replies when configured."),
    replay: bool = typer.Option(False, "--replay", help="Show the previous session before starting."),
    voice_input: Path | None = typer.Option(None, "--voice-input", help="Transcribe an audio file and use it as the first turn."),
    record_seconds: int = typer.Option(0, "--record-seconds", help="Record microphone input before the session when sounddevice is available."),
) -> None:
    settings, soul = _bootstrap()
    if replay:
        _show_last_session(settings)

    session_id = db.create_session(settings.database_url, soul.name)
    mood_engine = MoodEngine(settings)
    builder = ContextBuilder(settings, soul)
    client = LLMClient(settings, soul)
    post_processor = PostProcessor(settings)
    voice_bridge = VoiceBridge(settings)
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    current_mood: MoodSnapshot | None = None
    pending_inputs: list[str] = []
    voice_chat_mode = voice
    voice_output_enabled = voice
    voice_record_seconds = record_seconds if record_seconds > 0 else (6 if voice_chat_mode else 0)

    if voice_input:
        transcript = voice_bridge.transcribe(voice_input)
        if transcript.ok and transcript.text:
            pending_inputs.append(_normalize_voice_transcript(transcript.text))
            console.print(f"[dim]loaded voice input from {voice_input}[/dim]")
        else:
            console.print(f"[yellow]voice transcription unavailable: {transcript.error}[/yellow]")
    elif record_seconds > 0:
        captured = _capture_voice_input(voice_bridge, seconds=voice_record_seconds)
        if captured:
            pending_inputs.append(captured)

    try:
        _print_header(soul, session_id)
        while True:
            if pending_inputs:
                user_input = pending_inputs.pop(0)
                console.print(f"[bold cyan]You[/bold cyan]: {user_input}")
            else:
                try:
                    if voice_chat_mode:
                        typed_or_blank = Prompt.ask("[bold cyan]You[/bold cyan] (Enter=record)", default="").strip()
                        if typed_or_blank:
                            user_input = typed_or_blank
                        else:
                            captured = _capture_voice_input(voice_bridge, seconds=voice_record_seconds)
                            if captured:
                                user_input = captured
                                console.print(f"[bold cyan]You[/bold cyan]: {user_input}")
                            else:
                                user_input = Prompt.ask("[bold cyan]You[/bold cyan] (typed fallback)", default="").strip()
                    else:
                        user_input = Prompt.ask("[bold cyan]You[/bold cyan]").strip()
                except (KeyboardInterrupt, EOFError):
                    console.print()
                    break

            if not user_input:
                continue

            if user_input.startswith("/"):
                should_quit, updated_voice_output = _handle_session_command(
                    user_input,
                    settings=settings,
                    session_id=session_id,
                    current_mood=current_mood,
                    voice_enabled=voice_output_enabled,
                    episodic_repo=episodic_repo,
                )
                voice_output_enabled = updated_voice_output
                if should_quit:
                    break
                continue

            current_mood = mood_engine.analyze(user_input, user_id=settings.user_id)
            console.print(
                f"[dim]{soul.name} mood[/dim] "
                f"[magenta]{current_mood.companion_state}[/magenta] "
                f"[dim](user: {current_mood.user_mood})[/dim]"
            )
            db.log_message(
                settings.database_url,
                session_id=session_id,
                role="user",
                content=user_input,
                user_mood=current_mood.user_mood,
                companion_state=current_mood.companion_state,
                provider="local",
                metadata={"confidence": current_mood.confidence, "rationale": current_mood.rationale},
            )

            bundle = builder.build(session_id=session_id, user_input=user_input, mood=current_mood)
            result = _render_live_reply(
                client,
                speaker_name=soul.name,
                system_prompt=bundle.system_prompt,
                messages=bundle.messages,
                mood=current_mood,
            )
            _voice_output(voice_bridge, voice_output_enabled, result.text)

            db.log_message(
                settings.database_url,
                session_id=session_id,
                role="assistant",
                content=result.text,
                user_mood=current_mood.user_mood,
                companion_state=current_mood.companion_state,
                provider=result.provider,
                metadata={
                    "model": result.model,
                    "fallback_used": result.fallback_used,
                    "error": result.error,
                },
            )
            post_processor.process_turn(
                session_id=session_id,
                user_text=user_input,
                assistant_text=result.text,
                mood=current_mood,
            )
    finally:
        db.close_session(settings.database_url, session_id)
        post_processor.process_session_end(session_id=session_id)


@memories_app.callback(invoke_without_command=True)
def memories_list(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    memories = episodic_repo.list_top(limit=120)
    if not memories:
        console.print("[dim]No memories stored yet.[/dim]")
        return

    table = Table(title="Recent memories - sorted by HMS score", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Bar", style="magenta", width=14)
    table.add_column("Tier", style="magenta", width=10)
    table.add_column("When", style="cyan", width=20)
    table.add_column("Content", style="white")
    tier_counts = {"vivid": 0, "present": 0, "fading": 0, "cold": 0}
    for item in memories[:60]:
        score = _record_hms_score(item)
        tier = _record_tier(item)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        timestamp = str(item.metadata.get("timestamp") or "-")
        table.add_row(f"{score:.2f}", _score_bar(score), tier, timestamp, str(item.content))
    console.print(table)
    console.print(
        f"[dim]{tier_counts.get('vivid', 0)} vivid[/dim]  "
        f"[dim]{tier_counts.get('present', 0)} present[/dim]  "
        f"[dim]{tier_counts.get('fading', 0)} fading[/dim]  "
        f"[dim]{tier_counts.get('cold', 0)} cold[/dim]"
    )


@memories_app.command("search")
def memories_search(query: str = typer.Argument(..., help="Search text.")) -> None:
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    ranked = episodic_repo.search(query, limit=20)
    if not ranked:
        manual = db.search_memories(settings.database_url, query, limit=10)
        if manual:
            table = Table(title=f'Memory Search: "{query}" (legacy fallback)', box=box.SIMPLE_HEAVY)
            table.add_column("Source", style="cyan", width=10)
            table.add_column("Label", style="magenta", width=16)
            table.add_column("Content", style="white")
            for item in manual:
                table.add_row("manual", str(item["label"]), str(item["content"]))
            console.print(table)
            return
        console.print("[dim]No matching memories found.[/dim]")
        return

    table = Table(title=f'Semantic Memory Search: "{query}" (HMS reranked)', box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Tier", style="magenta", width=10)
    table.add_column("Content", style="white")
    table.add_column("Rank", style="cyan", width=8)
    for item in ranked[:20]:
        score = _record_hms_score(item)
        tier = _record_tier(item)
        rank = str(item.metadata.get("retrieval_rank", "-"))
        table.add_row(
            f"{score:.2f}",
            tier,
            str(item.content),
            rank,
        )
    console.print(table)


@memories_app.command("top")
def memories_top() -> None:
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    rows = episodic_repo.list_top(limit=10)
    if not rows:
        console.print("[dim]No memories stored yet.[/dim]")
        return
    table = Table(title="Top Memories (Most Vivid)", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Tier", style="magenta", width=10)
    table.add_column("Content", style="white")
    for row in rows:
        table.add_row(f"{_record_hms_score(row):.2f}", _record_tier(row), str(row.content))
    console.print(table)


@memories_app.command("cold")
def memories_cold() -> None:
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    rows = episodic_repo.list_cold(limit=50)
    if not rows:
        console.print("[dim]No cold memories yet.[/dim]")
        return
    table = Table(title="Cold Memories", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("When", style="cyan", width=20)
    table.add_column("Content", style="white")
    for row in rows:
        table.add_row(f"{_record_hms_score(row):.2f}", str(row.metadata.get("timestamp", "-")), str(row.content))
    console.print(table)


@memories_app.command("boost")
def memories_boost(query: str = typer.Argument(..., help="Query to match and boost memory.")) -> None:
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    matches = episodic_repo.search(query, limit=5)
    if not matches:
        console.print("[dim]No matching memories found.[/dim]")
        return
    target = matches[0]
    memory_id = str(target.metadata.get("memory_id", target.id))
    before = _record_hms_score(target)
    updated = episodic_repo.boost(memory_id)
    after = float(updated["hms_score"]) if updated and "hms_score" in updated else before
    console.print(f"[green]Boosted memory.[/green] {before:.2f} -> {after:.2f}")
    console.print(f"[dim]{target.content}[/dim]")


@memories_app.command("clear")
def memories_clear() -> None:
    settings, _ = _bootstrap()
    confirmed = Confirm.ask("Wipe all stored memories?", default=False)
    if not confirmed:
        console.print("[dim]Cancelled.[/dim]")
        return
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    deleted = db.clear_memories(settings.database_url)
    vector_deleted = episodic_repo.clear()
    console.print(f"[green]Deleted {deleted} SQL memories and {vector_deleted} episodic/vector entries.[/green]")


def _record_hms_score(record) -> float:
    raw = record.metadata.get("hms_score", 0.5)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.5


def _record_tier(record) -> str:
    return str(record.metadata.get("tier", "present"))


def _score_bar(score: float, width: int = 12) -> str:
    filled = int(max(0, min(width, round(score * width))))
    return ("█" * filled) + ("░" * (width - filled))


@story_app.callback(invoke_without_command=True)
def story_show(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    settings, _ = _bootstrap()
    _render_story(settings.user_story_file)


@story_app.command("edit")
def story_edit() -> None:
    settings, _ = _bootstrap()
    story_file = settings.user_story_file
    story_file.parent.mkdir(parents=True, exist_ok=True)
    if not story_file.exists():
        story_file.write_text("{}\n", encoding="utf-8")

    editor = os.environ.get("SOUL_EDITOR") or os.environ.get("VISUAL") or os.environ.get("EDITOR")

    console.print(f"Story file: [cyan]{story_file}[/cyan]")
    if not editor:
        console.print("[yellow]No editor configured. Set SOUL_EDITOR, VISUAL, or EDITOR to launch one automatically.[/yellow]")
        return

    try:
        command = [*shlex.split(editor, posix=os.name != "nt"), str(story_file)]
        subprocess.run(command, check=False)
    except FileNotFoundError:
        console.print(f"[yellow]Editor not found: {editor}[/yellow]")


@app.command()
def drift() -> None:
    settings, _ = _bootstrap()
    repo = DriftLogRepository(settings.drift_log_file)
    runs = repo.load()
    if not runs:
        console.print("[dim]No drift runs recorded yet.[/dim]")
        return
    table = Table(title="Drift History", box=box.SIMPLE_HEAVY)
    table.add_column("Date", style="cyan", width=14)
    table.add_column("Before", style="white")
    table.add_column("After", style="white")
    for row in runs[-20:]:
        table.add_row(row.run_date, json.dumps(row.dimensions_before), json.dumps(row.dimensions_after))
    console.print(table)


@app.command()
def milestones() -> None:
    settings, _ = _bootstrap()
    rows = db.list_milestones(settings.database_url)
    if not rows:
        console.print("[dim]No milestones recorded yet.[/dim]")
        return
    table = Table(title="Relationship Timeline", box=box.SIMPLE_HEAVY)
    table.add_column("When", style="cyan", width=20)
    table.add_column("Kind", style="magenta", width=24)
    table.add_column("Note", style="white")
    for row in rows:
        table.add_row(str(row["occurred_at"]), str(row["kind"]), str(row["note"]))
    console.print(table)


@app.command()
def status() -> None:
    settings, soul = _bootstrap()
    mood_engine = MoodEngine(settings)
    voice_bridge = VoiceBridge(settings)
    telegram_runner = TelegramBotRunner(settings=settings)
    story_repo = UserStoryRepository(settings.user_story_file)
    last_message_at = db.get_last_message_timestamp(settings.database_url)
    total_sessions = db.count_sessions(settings.database_url)
    total_messages = db.count_messages(settings.database_url)

    now = datetime.now(timezone.utc)
    days_since_last_chat: int | None = None
    if last_message_at:
        timestamp = datetime.fromisoformat(last_message_at)
        delta = now - timestamp
        days_since_last_chat = delta.days

    stress_events = db.list_user_message_moods_since(
        settings.database_url,
        moods=("stressed", "overwhelmed", "venting"),
        since=(now.replace(microsecond=0) - timedelta(days=14)).isoformat(),
    )
    stress_signal_dates = [str(item["created_at"]) for item in stress_events]
    milestones_today: list[str] = []
    for milestone in db.list_milestones(settings.database_url, limit=200):
        occurred_at = str(milestone.get("occurred_at", ""))
        try:
            occurred = datetime.fromisoformat(occurred_at)
        except ValueError:
            continue
        if (occurred.month, occurred.day) == (now.month, now.day):
            milestones_today.append(str(milestone.get("note") or milestone.get("kind") or "Milestone"))
    first_sessions = db.list_sessions(settings.database_url, limit=1)
    if first_sessions:
        first_started = str(first_sessions[0].get("started_at", ""))
        try:
            first_date = datetime.fromisoformat(first_started)
        except ValueError:
            first_date = None
        if first_date and first_date.year < now.year and (first_date.month, first_date.day) == (now.month, now.day):
            milestones_today.append("relationship anniversary")

    candidates = build_reach_out_candidates(
        days_since_last_chat=days_since_last_chat,
        story=story_repo.load(),
        today=now,
        stress_signal_dates=stress_signal_dates,
        milestones_today=milestones_today,
    )
    save_reach_out_candidates(settings.reach_out_candidates_file, candidates)

    current_state = mood_engine.current_state(settings.user_id) or {}
    table = Table(title="SOUL Status", box=box.SIMPLE_HEAVY)
    table.add_column("Field", style="magenta", width=22)
    table.add_column("Value", style="white")
    table.add_row("Companion", soul.name)
    table.add_row("Database", settings.database_url)
    table.add_row("Environment", settings.environment)
    table.add_row("Total sessions", str(total_sessions))
    table.add_row("Total messages", str(total_messages))
    table.add_row("Days since last chat", "never" if days_since_last_chat is None else str(days_since_last_chat))
    table.add_row("Companion mood", str(current_state.get("state", "unknown")))
    table.add_row("Reach-out candidates", str(len(load_reach_out_candidates(settings.reach_out_candidates_file))))
    table.add_row("Voice", voice_bridge.status()["voice"])
    table.add_row("Telegram", telegram_runner.status()["telegram"])
    table.add_row("Next milestone", _next_milestone_label(settings, total_messages))
    console.print(table)


@app.command("run-jobs")
def run_jobs() -> None:
    settings, _ = _bootstrap()
    story_repo = UserStoryRepository(settings.user_story_file)
    results = consolidate_pending_sessions(
        database_url=settings.database_url,
        story_path=settings.user_story_file,
        memory_path=settings.episodic_memory_file,
        shared_language_path=settings.shared_language_file,
        ledger_path=settings.consolidation_ledger_file,
        source="manual",
        settings=settings,
    )
    decay = run_hms_decay()
    archive = archive_and_purge_old_session_messages(
        database_url=settings.database_url,
        archive_dir=settings.session_archive_dir,
        retention_days=settings.raw_retention_days,
    )
    resonance_signals = derive_resonance_signals(settings.database_url)
    drift_result = run_drift_task(
        personality_path=settings.personality_file,
        log_path=settings.drift_log_file,
        resonance_signals=resonance_signals,
    )
    reflection_entry = generate_monthly_reflection(settings)
    last_message_at = db.get_last_message_timestamp(settings.database_url)
    now = datetime.now(timezone.utc)
    days_since_last_chat = None
    if last_message_at:
        timestamp = datetime.fromisoformat(last_message_at)
        days_since_last_chat = (now - timestamp).days
    stress_events = db.list_user_message_moods_since(
        settings.database_url,
        moods=("stressed", "overwhelmed", "venting"),
        since=(now.replace(microsecond=0) - timedelta(days=14)).isoformat(),
    )
    stress_signal_dates = [str(item["created_at"]) for item in stress_events]
    milestones_today: list[str] = []
    for milestone in db.list_milestones(settings.database_url, limit=200):
        occurred_at = str(milestone.get("occurred_at", ""))
        try:
            occurred = datetime.fromisoformat(occurred_at)
        except ValueError:
            continue
        if (occurred.month, occurred.day) == (now.month, now.day):
            milestones_today.append(str(milestone.get("note") or milestone.get("kind") or "Milestone"))
    first_sessions = db.list_sessions(settings.database_url, limit=1)
    if first_sessions:
        first_started = str(first_sessions[0].get("started_at", ""))
        try:
            first_date = datetime.fromisoformat(first_started)
        except ValueError:
            first_date = None
        if first_date and first_date.year < now.year and (first_date.month, first_date.day) == (now.month, now.day):
            milestones_today.append("relationship anniversary")
    candidates = build_reach_out_candidates(
        days_since_last_chat=days_since_last_chat,
        story=story_repo.load(),
        today=now,
        stress_signal_dates=stress_signal_dates,
        milestones_today=milestones_today,
    )
    save_reach_out_candidates(settings.reach_out_candidates_file, candidates)
    delivery = dispatch_reach_out_candidates(settings, candidates)
    console.print(
        "[green]Maintenance run completed.[/green] "
        f"sessions={len(results)} "
        f"memories={sum(int(item['memories_added']) for item in results)} "
        f"drift_dims={len(drift_result.updated)} "
        f"reflection={'1' if reflection_entry else '0'} "
        f"reach_outs={len(candidates)} "
        f"delivered={delivery['sent']} "
        f"decay_updated={decay['updated']} "
        f"cold_moved={decay['moved_to_cold']} "
        f"archived={archive['archived_sessions']} "
        f"purged={archive['purged_messages']}"
    )


@app.command("telegram-bot")
def telegram_bot() -> None:
    runner = TelegramBotRunner(settings=get_settings())
    status_map = runner.status()
    table = Table(title="SOUL Telegram Bot", box=box.SIMPLE_HEAVY)
    table.add_column("Component", style="magenta")
    table.add_column("State", style="white")
    for key, value in status_map.items():
        table.add_row(key, value)
    console.print(table)
    if status_map["telegram"].startswith("disabled"):
        raise typer.Exit(code=0)
    runner.run_forever()


@db_app.callback(invoke_without_command=True)
def db_default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    db_init()


@db_app.command("init")
def db_init() -> None:
    settings = get_settings()
    _ensure_runtime_files(settings)
    db.init_db(settings.database_url)
    console.print(f"[green]Initialized database at {settings.database_url}[/green]")


@app.command()
def config() -> None:
    settings = get_settings()
    console.print_json(json.dumps(settings.as_redacted_dict(), indent=2))


@app.command()
def version() -> None:
    console.print(f"SOUL {__version__}")


def _next_milestone_label(settings: Settings, total_messages: int) -> str:
    checks = [
        ("hundredth_message", f"100th message ({max(0, 100 - total_messages)} away)"),
        ("seven_day_streak", "7-day conversation streak"),
        ("first_recurring_phrase", "first recurring phrase"),
        ("one_month_anniversary", "1-month anniversary"),
        ("three_month_anniversary", "3-month anniversary"),
    ]
    for kind, label in checks:
        if kind == "hundredth_message" and total_messages >= 100:
            continue
        if not db.milestone_exists(settings.database_url, kind):
            return label
    return "relationship timeline is active"


def main() -> None:
    app()


if __name__ == "__main__":
    main()
