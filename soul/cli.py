from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from soul import __version__, db
from soul.bootstrap import FeatureInitializationError, TurnExecutionError, validate_startup
from soul.conversation.orchestrator import ConversationOrchestrator
from soul.config import Settings, get_settings
from soul.core.context_builder import ContextBuilder
from soul.core.llm_client import LLMClient, LLMResult
from soul.core.mood_engine import MoodEngine, MoodSnapshot
from soul.core.presence_context import build_presence_context, runtime_now
from soul.core.post_processor import PostProcessor
from soul.core.skill_templates import get_builtin_skill_template, list_builtin_skill_templates, read_builtin_skill_template
from soul.core.soul_loader import Soul, load_soul
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.mood import MoodSnapshotsRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.memory.repositories.proactive import ProactiveCandidateRepository
from soul.memory.repositories.user_facts import UserFactsRepository
from soul.maintenance.consolidation import consolidate_pending_sessions
from soul.maintenance.decay import run_hms_decay
from soul.maintenance.drift import derive_resonance_signals, run_drift_task
from soul.maintenance.jobs import run_enabled_maintenance, trigger_maintenance_if_due
from soul.maintenance.proactive import ReachOutCandidate, dispatch_reach_out_candidates, refresh_proactive_candidates
from soul.maintenance.reflection import generate_monthly_reflection
from soul.observability.traces import TurnTraceRepository
from soul.presence.telegram import TelegramBotRunner
from soul.presence.voice import VoiceBridge
from soul.memory.user_story import UserStory


app = typer.Typer(help="SOUL, an AI companion from your terminal.", add_completion=False)
memories_app = typer.Typer(help="Memory commands.", invoke_without_command=True, no_args_is_help=False)
story_app = typer.Typer(help="User story commands.", invoke_without_command=True, no_args_is_help=False)
db_app = typer.Typer(help="Database commands.", invoke_without_command=True, no_args_is_help=False)
skills_app = typer.Typer(help="Workspace skill template commands.", invoke_without_command=True, no_args_is_help=False)
debug_app = typer.Typer(help="Debug inspection commands.", invoke_without_command=True, no_args_is_help=False)
app.add_typer(memories_app, name="memories")
app.add_typer(story_app, name="story")
app.add_typer(db_app, name="db")
app.add_typer(skills_app, name="skills")
app.add_typer(debug_app, name="debug")

console = Console(width=120)


def _relative_time(iso_str: str) -> str:
    """Convert an ISO-8601 timestamp string to a human-relative label."""
    if not iso_str or iso_str == "-":
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    days = delta.days
    if days < 0:
        return "just now"
    if days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            mins = delta.seconds // 60
            return f"{mins}m ago" if mins > 0 else "just now"
        return f"{hours}h ago"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 14:
        return "1 week ago"
    if days < 30:
        return f"{days // 7} weeks ago"
    if days < 60:
        return "1 month ago"
    months = days // 30
    if months < 12:
        return f"{months} months ago"
    years = days // 365
    return f"{years} year{'s' if years > 1 else ''} ago"


def _parse_iso_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_countdown(count: int, singular: str, plural: str | None = None) -> str:
    plural = plural or f"{singular}s"
    unit = singular if count == 1 else plural
    return f"{count} {unit} away"


def _message_milestone_label(count: int) -> str:
    if count == 100:
        return "100th message"
    return f"{count}-message milestone"


def _bootstrap() -> tuple[Settings, Soul]:
    settings = get_settings()
    _ensure_runtime_files(settings)
    validate_startup(settings)
    soul = load_soul(settings.soul_file)
    return settings, soul


def _ensure_runtime_files(settings: Settings) -> None:
    def _mkdir_secure(path: Path) -> None:
        """Create directory with restrictive permissions (rwx-------)."""
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass

    def _write_secure(path: Path, content: str) -> None:
        """Write file and immediately restrict to owner-only (rw-------)."""
        path.write_text(content, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    _mkdir_secure(settings.soul_data_dir)
    if settings.database_is_sqlite:
        _mkdir_secure(settings.sqlite_path.parent)
    _mkdir_secure(settings.session_log_dir)
    _mkdir_secure(settings.session_archive_dir)
    _mkdir_secure(settings.exports_dir)
    _mkdir_secure(settings.temp_dir)

    if not settings.soul_file.exists():
        _write_secure(settings.soul_file, settings.default_soul_yaml)
        try:
            settings.soul_file.chmod(0o600)
        except OSError:
            pass


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
    emitted_chunks = False

    def handle_chunk(chunk: str) -> None:
        nonlocal emitted_chunks
        if not chunk:
            return
        emitted_chunks = True
        console.print(Text(chunk, style="white"), end="", soft_wrap=True)
        console.file.flush()

    console.print(f"[bold magenta]{speaker_name}[/bold magenta] > ", end="")
    result = client.reply(
        system_prompt=system_prompt,
        messages=messages,
        mood=mood,
        stream_handler=handle_chunk,
    )
    if not emitted_chunks and result.text:
        console.print(Text(result.text, style="white"), end="", soft_wrap=True)
    console.print()
    return result


def _render_static_reply(
    *,
    speaker_name: str,
    text: str,
    provider: str,
    model: str,
) -> LLMResult:
    console.print(f"[bold magenta]{speaker_name}[/bold magenta] > {text}")
    return LLMResult(text=text, provider=provider, model=model, fallback_used=False)


def _print_turn_trace(soul: Soul, mood: MoodSnapshot, bundle: object) -> None:
    messages = getattr(bundle, "messages", [])
    story_summary = getattr(bundle, "story_summary", None)
    memory_snippets = getattr(bundle, "memory_snippets", []) or []
    history_count = max(0, len(messages) - 1)
    story_state = "loaded" if story_summary else "empty"
    memory_count = len(memory_snippets)

    console.print(
        f"[dim]inside {soul.name}[/dim] "
        f"[magenta]{mood.companion_state}[/magenta] "
        f"[dim](user: {mood.user_mood}, history: {history_count}, story: {story_state}, memories: {memory_count})[/dim]"
    )
    console.print(f"[dim]{soul.name} is thinking through the reply...[/dim]")


def _run_orchestrated_turn(
    orchestrator: ConversationOrchestrator,
    *,
    soul: Soul,
    session_id: str,
    user_input: str,
) -> tuple[object, MoodSnapshot]:
    emitted_chunks = False
    observed_mood: MoodSnapshot | None = None

    def handle_chunk(chunk: str) -> None:
        nonlocal emitted_chunks
        if not chunk:
            return
        emitted_chunks = True
        console.print(Text(chunk, style="white"), end="", soft_wrap=True)
        console.file.flush()

    def before_generate(mood: MoodSnapshot, bundle: object) -> None:
        nonlocal observed_mood
        observed_mood = mood
        console.print(
            f"[dim]{soul.name} mood[/dim] "
            f"[magenta]{mood.companion_state}[/magenta] "
            f"[dim](user: {mood.user_mood})[/dim]"
        )
        _print_turn_trace(soul, mood, bundle)

    console.print(f"[bold magenta]{soul.name}[/bold magenta] > ", end="")
    result = orchestrator.run_turn(
        session_id=session_id,
        user_text=user_input,
        stream_handler=handle_chunk,
        before_generate=before_generate,
    )
    if not emitted_chunks and result.llm_result.text:
        console.print(Text(result.llm_result.text, style="white"), end="", soft_wrap=True)
    console.print()
    return result, observed_mood or result.mood


def _show_last_session(settings: Settings) -> None:
    session_id = db.get_last_completed_session_id(settings.database_url)
    if not session_id:
        console.print("[dim]No previous session found.[/dim]")
        return

    rows = db.get_session_messages(settings.database_url, session_id)
    table = Table(title="Last Session Replay", box=box.SIMPLE_HEAVY)
    table.add_column("Role", style="cyan", width=10)
    table.add_column("Message", style="white")
    for row in rows:
        table.add_row(str(row["role"]), str(row["content"]))
    console.print(table)


def _render_story(settings: Settings) -> None:
    payload = UserFactsRepository(settings.database_url, user_id=settings.user_id).export_story_payload()
    chapter = payload.get("current_chapter") or {}
    has_content = (
        bool(chapter.get("summary"))
        or bool(chapter.get("active_goals"))
        or bool(chapter.get("active_fears"))
        or bool(payload.get("big_moments"))
        or bool(payload.get("relationships"))
        or bool(payload.get("values_observed"))
        or bool(payload.get("things_they_love"))
        or bool(payload.get("upcoming_events"))
        or bool(payload.get("triggers"))
    )
    if not has_content:
        console.print("[dim]No user story exists yet.[/dim]")
        return

    table = Table(title="User Story", box=box.SIMPLE_HEAVY, show_header=False)
    table.add_column("Field", style="magenta", width=20)
    table.add_column("Value", style="white")

    if chapter.get("summary"):
        table.add_row("Chapter", str(chapter["summary"]))
    if chapter.get("current_mood_trend"):
        table.add_row("Mood trend", str(chapter["current_mood_trend"]))
    if chapter.get("active_goals"):
        table.add_row("Goals", ", ".join(str(g) for g in chapter["active_goals"]))
    if chapter.get("active_fears"):
        table.add_row("Fears", ", ".join(str(f) for f in chapter["active_fears"]))

    basics = payload.get("basics") or {}
    if basics.get("birthday"):
        table.add_row("Birthday", str(basics["birthday"]))

    for field, label in [
        ("big_moments", "Big moments"),
        ("relationships", "Relationships"),
        ("values_observed", "Values"),
        ("things_they_love", "Things they love"),
        ("upcoming_events", "Upcoming events"),
        ("triggers", "Triggers"),
    ]:
        items = payload.get(field) or []
        if items:
            if isinstance(items[0], dict):
                lines = []
                for item in items:
                    parts = [str(v) for v in item.values() if v]
                    lines.append("  ".join(parts))
                table.add_row(label, "\n".join(lines))
            else:
                table.add_row(label, ", ".join(str(i) for i in items))

    updated = str(payload.get("updated_at", ""))[:10]
    if updated:
        table.add_row("Last updated", updated)

    console.print(table)


def _refresh_reach_out_candidates(settings: Settings) -> None:
    """Refresh reach-out candidates on chat startup via SQLite-backed storage."""
    if not settings.enable_proactive:
        return
    refresh_proactive_candidates(settings, channel="cli")


def _show_pending_reach_outs(settings: Settings, soul: Soul) -> None:
    """Show pending CLI reach-out messages once, then clear them."""
    if settings.enable_telegram:
        return

    repo = ProactiveCandidateRepository(settings.database_url, user_id=settings.user_id)
    rows = repo.list_pending(channel="cli", limit=settings.chat_pending_reach_out_limit)
    if not rows:
        return

    for row in rows:
        console.print()
        console.print(
            Panel(
                f"[italic]{row['message']}[/italic]",
                title=f"[dim]{soul.name}[/dim]",
                box=box.SIMPLE,
                border_style="magenta",
            )
        )
        console.print()

    for row in rows:
        repo.mark_delivered(str(row["id"]))


def _voice_output(voice_bridge: VoiceBridge, enabled: bool, text: str) -> None:
    if not enabled:
        return
    result = voice_bridge.speak(text, autoplay=True)
    played = bool(getattr(result, "played", False))
    if result.ok and played:
        console.print("[dim]voice played[/dim]")
    elif result.ok:
        console.print(f"[dim]voice saved to {result.output_path}[/dim]")
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


def _match_local_runtime_query(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", text.casefold().strip())
    clock_patterns = (
        r"\bwhat time is it\b",
        r"\bwhat(?:'s| is)? the time\b",
        r"\btime now\b",
        r"\bcurrent time\b",
        r"\btell me the time\b",
        r"\bwhat(?:'s| is)? the date\b",
        r"\bwhat(?:'s| is)? today(?:'s)? date\b",
        r"\bdate today\b",
        r"\bwhat day is (?:it|today)\b",
    )
    if any(re.search(pattern, normalized) for pattern in clock_patterns):
        return "clock"
    return None


def _local_runtime_mood(query_kind: str) -> MoodSnapshot:
    return MoodSnapshot(
        user_mood="curious",
        companion_state="curious",
        confidence=1.0,
        rationale=f"local runtime {query_kind} query",
    )


def _local_runtime_reply(settings: Settings, *, speaker_name: str, query_kind: str) -> LLMResult:
    local_now = runtime_now(settings)
    timezone_label = getattr(local_now.tzinfo, "key", None) or local_now.tzname() or settings.timezone_name
    clock_label = local_now.strftime("%I:%M %p").lstrip("0")
    date_label = local_now.strftime("%A, %B %d, %Y")
    if query_kind == "clock":
        text = f"It's {clock_label} on {date_label} ({timezone_label})."
    else:
        text = f"It's {clock_label} on {date_label} ({timezone_label})."
    return _render_static_reply(
        speaker_name=speaker_name,
        text=text,
        provider="local-runtime",
        model=f"runtime-{query_kind}",
    )


def _print_local_runtime_trace(soul: Soul, mood: MoodSnapshot, *, query_kind: str) -> None:
    console.print(
        f"[dim]inside {soul.name}[/dim] "
        f"[magenta]{mood.companion_state}[/magenta] "
        f"[dim](user: {mood.user_mood}, local: {query_kind})[/dim]"
    )
    console.print(f"[dim]{soul.name} is checking the local {query_kind}...[/dim]")


def _handle_session_command(
    raw_input: str,
    *,
    settings: Settings,
    session_id: str,
    current_mood: MoodSnapshot | None,
    voice_output_enabled: bool,
    voice_chat_mode: bool,
    voice_bridge: VoiceBridge,
    episodic_repo: EpisodicMemoryRepository,
) -> tuple[bool, bool, bool]:
    try:
        parts = shlex.split(raw_input)
    except ValueError as exc:
        console.print(f"[red]Invalid command syntax:[/red] {exc}")
        return False, voice_output_enabled, voice_chat_mode

    command = parts[0].casefold()

    if command == "/quit":
        console.print("\n[dim]See you next time.[/dim]")
        return True, voice_output_enabled, voice_chat_mode

    if command == "/mood":
        if current_mood is None:
            console.print("[dim]No mood has been detected yet in this session.[/dim]")
        else:
            console.print(
                f"[cyan]user_mood[/cyan]={current_mood.user_mood}  "
                f"[magenta]companion_state[/magenta]={current_mood.companion_state}  "
                f"[dim]{current_mood.rationale}[/dim]"
            )
        return False, voice_output_enabled, voice_chat_mode

    if command == "/story":
        _render_story(settings)
        return False, voice_output_enabled, voice_chat_mode

    if command == "/save":
        note = raw_input[len("/save"):].strip()
        if not note:
            console.print("[red]Usage:[/red] /save note text")
            return False, voice_output_enabled, voice_chat_mode
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
                "label": "manual note",
            },
        )
        memory_id = str(saved.metadata.get("memory_id", saved.id))
        boosted = episodic_repo.boost(memory_id)
        score = float(boosted["hms_score"]) if boosted and "hms_score" in boosted else float(saved.metadata.get("hms_score", 0.5))
        console.print(f"[green]Saved and boosted memory.[/green] HMS={score:.2f}")
        return False, voice_output_enabled, voice_chat_mode

    if command == "/voice":
        requested = parts[1].casefold() if len(parts) > 1 else ""
        if requested not in {"on", "off"}:
            console.print("[red]Usage:[/red] /voice on|off")
            return False, voice_output_enabled, voice_chat_mode

        if requested == "off":
            voice_output_enabled = False
            voice_chat_mode = False
            console.print("[green]Voice input and output disabled for this session.[/green]")
            return False, voice_output_enabled, voice_chat_mode

        if not settings.enable_voice:
            console.print("[yellow]Voice feature is disabled. Set ENABLE_VOICE=true to use /voice on.[/yellow]")
            return False, voice_output_enabled, voice_chat_mode
        voice_output_enabled = True
        if getattr(voice_bridge, "can_record", True):
            voice_chat_mode = True
            console.print("[green]Voice input and output enabled for this session.[/green]")
        else:
            voice_chat_mode = False
            console.print(
                "[yellow]Microphone recording unavailable (sounddevice not installed). "
                "Voice output enabled for this session - type your input normally.[/yellow]"
            )
        return False, voice_output_enabled, voice_chat_mode

    console.print(f"[red]Unknown command:[/red] {command}")
    return False, voice_output_enabled, voice_chat_mode


@app.command()
def chat(
    voice: bool = typer.Option(False, "--voice", help="Synthesize assistant replies when configured."),
    replay: bool = typer.Option(False, "--replay", help="Show the previous session before starting."),
    voice_input: Path | None = typer.Option(None, "--voice-input", help="Transcribe an audio file and use it as the first turn."),
    record_seconds: int = typer.Option(0, "--record-seconds", help="Record microphone input before the session when sounddevice is available."),
) -> None:
    """Start an interactive chat session with your AI companion."""
    settings, soul = _bootstrap()
    if voice and not settings.enable_voice:
        console.print("[yellow]Voice feature is disabled. Set ENABLE_VOICE=true to use --voice.[/yellow]")
        raise typer.Exit(code=1)
    if (voice_input or record_seconds > 0) and not settings.enable_voice:
        console.print("[yellow]Voice feature is disabled. Set ENABLE_VOICE=true to use voice input.[/yellow]")
        raise typer.Exit(code=1)
    _refresh_reach_out_candidates(settings)
    if replay:
        _show_last_session(settings)

    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)
    trace_repo = TurnTraceRepository(settings.database_url, user_id=settings.user_id)
    session_id = messages_repo.create_session(soul.name)
    orchestrator = ConversationOrchestrator(settings, soul)
    mood_repo = MoodSnapshotsRepository(settings.database_url, user_id=settings.user_id)
    voice_bridge = VoiceBridge(settings)
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    current_mood: MoodSnapshot | None = None
    pending_inputs: list[str] = []
    voice_chat_mode = voice
    voice_output_enabled = voice
    if voice_chat_mode and not getattr(voice_bridge, "can_record", True):
        console.print(
            "[yellow]Microphone recording unavailable (sounddevice not installed). "
            "Voice mode active for output only - type your input normally.[/yellow]"
        )
        voice_chat_mode = False
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
        _show_pending_reach_outs(settings, soul)
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
                should_quit, updated_voice_output, updated_voice_chat_mode = _handle_session_command(
                    user_input,
                    settings=settings,
                    session_id=session_id,
                    current_mood=current_mood,
                    voice_output_enabled=voice_output_enabled,
                    voice_chat_mode=voice_chat_mode,
                    voice_bridge=voice_bridge,
                    episodic_repo=episodic_repo,
                )
                voice_output_enabled = updated_voice_output
                voice_chat_mode = updated_voice_chat_mode
                if should_quit:
                    break
                continue

            runtime_query = _match_local_runtime_query(user_input)
            if runtime_query is not None:
                current_mood = _local_runtime_mood(runtime_query)

            if runtime_query is not None:
                console.print(
                    f"[dim]{soul.name} mood[/dim] "
                    f"[magenta]{current_mood.companion_state}[/magenta] "
                    f"[dim](user: {current_mood.user_mood})[/dim]"
                )
                user_message_id = messages_repo.log_message(
                    session_id=session_id,
                    role="user",
                    content=user_input,
                    user_mood=current_mood.user_mood,
                    companion_state=current_mood.companion_state,
                    provider="local",
                    metadata={
                        "confidence": current_mood.confidence,
                        "rationale": current_mood.rationale,
                        "word_count": len(user_input.split()),
                        "local_action": runtime_query,
                        "skip_memory": True,
                    },
                )
                mood_repo.add_snapshot(
                    session_id=session_id,
                    message_id=user_message_id,
                    user_mood=current_mood.user_mood,
                    companion_state=current_mood.companion_state,
                    confidence=current_mood.confidence,
                    rationale=current_mood.rationale,
                )
                _print_local_runtime_trace(soul, current_mood, query_kind=runtime_query)
                result = _local_runtime_reply(settings, speaker_name=soul.name, query_kind=runtime_query)
                _voice_output(voice_bridge, voice_output_enabled, result.text)
                assistant_message_id = messages_repo.log_message(
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
                        "local_action": runtime_query,
                    },
                )
                trace_repo.write_trace(
                    session_id=session_id,
                    input_message_id=user_message_id,
                    reply_message_id=assistant_message_id,
                    payload={
                        "retrieved_memories": [],
                        "retrieved_facts": None,
                        "personality_state": {},
                        "mood_snapshot": {
                            "user_mood": current_mood.user_mood,
                            "companion_state": current_mood.companion_state,
                            "confidence": current_mood.confidence,
                            "rationale": current_mood.rationale,
                        },
                        "prompt_sections": ["local_runtime"],
                        "provider": result.provider,
                        "model": result.model,
                        "local_action": runtime_query,
                        "response_latency_ms": 0.0,
                        "persisted_records": {},
                    },
                )
            else:
                try:
                    turn_result, current_mood = _run_orchestrated_turn(
                        orchestrator,
                        soul=soul,
                        session_id=session_id,
                        user_input=user_input,
                    )
                except TurnExecutionError as exc:
                    console.print()
                    console.print(f"[red]Turn failed.[/red] {exc}")
                    continue
                result = turn_result.llm_result
                _voice_output(voice_bridge, voice_output_enabled, result.text)
            console.print(f"[dim]-- {soul.name}: {current_mood.companion_state} | you: {current_mood.user_mood} --[/dim]")
    finally:
        messages_repo.close_session(session_id)
        orchestrator.post_processor.process_session_end(session_id=session_id)
        orchestrator.shutdown()
        trigger_maintenance_if_due(settings)


@memories_app.callback(invoke_without_command=True)
def memories_list(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    memories: list[dict[str, object]] = []
    for item in episodic_repo.list_top(limit=120):
        source = str(item.metadata.get("source") or "episodic")
        memories.append(
            {
                "source": source,
                "score": _record_hms_score(item),
                "tier": _record_tier(item),
                "when": _relative_time(str(item.metadata.get("timestamp") or "-")),
                "content": str(item.content),
            }
        )

    if not memories:
        console.print("[dim]No memories stored yet.[/dim]")
        return

    memories.sort(key=lambda item: float(item["score"]), reverse=True)
    table = Table(title="Recent memories - sorted by HMS score", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Bar", style="magenta", width=14)
    table.add_column("Tier", style="magenta", width=10)
    table.add_column("When", style="cyan", width=20)
    table.add_column("Content", style="white")
    tier_counts = {"vivid": 0, "present": 0, "fading": 0, "cold": 0, "manual": 0}
    for item in memories[:60]:
        score = float(item["score"])
        tier = str(item["tier"])
        source = str(item["source"])
        if source == "manual":
            tier_counts["manual"] = tier_counts.get("manual", 0) + 1
        else:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        table.add_row(f"{score:.2f}", _score_bar(score), tier, str(item["when"]), str(item["content"]))
    console.print(table)
    console.print(
        f"[dim]{tier_counts.get('vivid', 0)} vivid[/dim]  "
        f"[dim]{tier_counts.get('present', 0)} present[/dim]  "
        f"[dim]{tier_counts.get('fading', 0)} fading[/dim]  "
        f"[dim]{tier_counts.get('cold', 0)} cold[/dim]  "
        f"[dim]{tier_counts.get('manual', 0)} manual[/dim]"
    )


@skills_app.callback(invoke_without_command=True)
def skills_list(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    table = Table(title="Built-in Workspace Skills", box=box.SIMPLE_HEAVY)
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Description", style="white")
    for template in list_builtin_skill_templates():
        table.add_row(template.name, template.description)
    console.print(table)


@skills_app.command("init")
def skills_init(
    template_name: str = typer.Argument(..., help="Built-in skill template name."),
    directory: Path = typer.Option(Path("."), "--dir", help="Target workspace directory."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing SKILL.md."),
) -> None:
    """Write a built-in SKILL.md template into a workspace."""
    template = get_builtin_skill_template(template_name)
    if template is None:
        available = ", ".join(item.name for item in list_builtin_skill_templates())
        console.print(f"[red]Unknown skill template:[/red] {template_name}")
        console.print(f"[dim]Available templates: {available}[/dim]")
        raise typer.Exit(code=1)

    target_dir = directory.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "SKILL.md"
    if target_file.exists() and not force:
        console.print(f"[red]Refusing to overwrite existing file:[/red] {target_file}")
        console.print("[dim]Use --force if you want to replace it.[/dim]")
        raise typer.Exit(code=1)

    target_file.write_text(read_builtin_skill_template(template_name), encoding="utf-8")
    console.print(f"[green]Wrote workspace skill.[/green] {target_file}")


@memories_app.command("search")
def memories_search(query: str = typer.Argument(..., help="Search text.")) -> None:
    """Search memories by text and show HMS-reranked results."""
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    episodic = episodic_repo.search(query, limit=20)
    if not episodic:
        console.print("[dim]No matching memories found.[/dim]")
        return

    merged: list[dict[str, object]] = []
    for item in episodic:
        score = _record_hms_score(item)
        merged.append(
            {
                "source": str(item.metadata.get("source") or "episodic"),
                "score": score,
                "tier": _record_tier(item),
                "content": str(item.content),
                "rank": _record_retrieval_rank(item, query=query),
            }
        )

    merged.sort(key=lambda row: float(row["rank"]), reverse=True)

    table = Table(title=f'Unified Memory Search: "{query}" (HMS reranked)', box=box.SIMPLE_HEAVY)
    table.add_column("Source", style="cyan", width=18)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Tier", style="magenta", width=10)
    # Make content rendering stable for contract tests:
    # keep the cell wide enough to avoid wrapping into multiple lines.
    table.add_column("Content", style="white")
    table.add_column("Rank", style="cyan", width=8)

    for item in merged[:20]:
        table.add_row(
            str(item["source"]),
            f"{float(item['score']):.2f}",
            str(item["tier"]),
            str(item["content"]),
            f"{float(item['rank']):.4f}",
        )
    console.print(table)


@memories_app.command("top")
def memories_top() -> None:
    """Show the top-scoring (most vivid) memories."""
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    rows = episodic_repo.list_top(limit=10)
    if not rows:
        console.print("[dim]No memories stored yet.[/dim]")
        return
    table = Table(title="Top Memories (Most Vivid)", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Tier", style="magenta", width=10)
    table.add_column("Source", style="dim", width=18)
    table.add_column("Content", style="white")
    for row in rows:
        source = str(row.metadata.get("source") or "") if hasattr(row, "metadata") else ""
        table.add_row(f"{_record_hms_score(row):.2f}", _record_tier(row), source, str(row.content))
    console.print(table)


@memories_app.command("cold")
def memories_cold() -> None:
    """Show cold (low-score, fading) memories."""
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    rows = episodic_repo.list_cold(limit=50)
    if not rows:
        console.print("[dim]No cold memories yet.[/dim]")
        return
    table = Table(title="Cold Memories", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("When", style="cyan", width=20)
    table.add_column("Content", style="white")
    for row in rows:
        table.add_row(
            f"{_record_hms_score(row):.2f}",
            _relative_time(str(row.metadata.get("timestamp", "-"))),
            str(row.content),
        )
    console.print(table)


@memories_app.command("boost")
def memories_boost(query: str = typer.Argument(..., help="Query to match and boost memory.")) -> None:
    """Boost the HMS score of the best-matching memory."""
    settings, _ = _bootstrap()
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    matches = episodic_repo.search(query, limit=5)
    if not matches:
        console.print("[dim]No matching memories found.[/dim]")
        return
    target = matches[0]
    memory_id = str(target.metadata.get("memory_id", target.id))
    before_row = episodic_repo.get_row(memory_id)
    before = float(before_row["hms_score"]) if before_row and "hms_score" in before_row else _record_hms_score(target)
    updated = episodic_repo.boost(memory_id)
    after = float(updated["hms_score"]) if updated and "hms_score" in updated else before
    console.print(f"[green]Boosted memory.[/green] {before:.3f} -> {after:.3f}")
    console.print(f"[dim]{target.content}[/dim]")


@memories_app.command("clear")
def memories_clear() -> None:
    """Wipe all stored memories for the current user."""
    settings, _ = _bootstrap()
    confirmed = Confirm.ask("Wipe all stored memories?", default=False)
    if not confirmed:
        console.print("[dim]Cancelled.[/dim]")
        return
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    deleted = episodic_repo.clear()
    console.print(f"[green]Deleted {deleted} SQLite-backed memories.[/green]")


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
    return ("#" * filled) + ("." * (width - filled))


def _record_retrieval_rank(record, *, query: str) -> float:
    raw = record.metadata.get("retrieval_rank")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    settings = get_settings()
    semantic = _simple_similarity(query, str(record.content))
    return (semantic * settings.hms_semantic_weight) + (_record_hms_score(record) * settings.hms_score_weight)


def _simple_similarity(query: str, content: str) -> float:
    settings = get_settings()
    query_tokens = {token.casefold() for token in query.split() if token.strip()}
    if not query_tokens:
        return 0.0
    content_tokens = {token.casefold() for token in content.split() if token.strip()}
    overlap = len(query_tokens & content_tokens) / max(1, len(query_tokens))
    if query.casefold() in content.casefold():
        overlap += settings.memory_substring_boost
    return _clamp01(overlap)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@story_app.callback(invoke_without_command=True)
def story_show(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    settings, _ = _bootstrap()
    _render_story(settings)


@story_app.command("edit")
def story_edit() -> None:
    """Open the user story in an external editor for manual editing."""
    settings, _ = _bootstrap()
    story_repo = UserFactsRepository(settings.database_url, user_id=settings.user_id)
    payload = story_repo.export_story_payload()
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    story_file = settings.temp_dir / f"soul-story-edit-{settings.user_id}.json"
    story_file.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    editor = os.environ.get("SOUL_EDITOR") or os.environ.get("VISUAL") or os.environ.get("EDITOR")

    console.print(f"Story file: [cyan]{story_file}[/cyan]")
    if not editor:
        console.print("[yellow]No editor configured. Set SOUL_EDITOR, VISUAL, or EDITOR to launch one automatically.[/yellow]")
        try:
            story_file.unlink(missing_ok=True)
        except OSError:
            pass
        return

    try:
        command = [*shlex.split(editor, posix=os.name != "nt"), str(story_file)]
        subprocess.run(command, check=False)
        updated = json.loads(story_file.read_text(encoding="utf-8"))
        story_repo.import_story_payload(updated, source="story_edit")
        archive_dir = settings.exports_dir / "story-edit-archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived = archive_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{settings.user_id}.json"
        archived.write_text(json.dumps(updated, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    except FileNotFoundError:
        console.print(f"[yellow]Editor not found: {editor}[/yellow]")
    finally:
        try:
            story_file.unlink(missing_ok=True)
        except OSError:
            pass


@app.command()
def drift() -> None:
    """Show personality drift history over time."""
    settings, _ = _bootstrap()
    runs = PersonalityStateRepository(settings.database_url, user_id=settings.user_id).list_history(limit=21)
    if not runs:
        console.print("[dim]No drift runs recorded yet.[/dim]")
        return
    # list_history returns newest-first; reverse to get chronological order
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
        table.add_row(
            str(row.get("created_at", ""))[:10],
            state_str,
            sig_str,
        )
    console.print(table)


@app.command()
def milestones() -> None:
    """Show relationship milestones and timeline."""
    settings, _ = _bootstrap()
    rows = db.list_milestones(settings.database_url)
    if not rows:
        console.print("[dim]No milestones recorded yet.[/dim]")
        return
    table = Table(title="Relationship Timeline", box=box.SIMPLE_HEAVY)
    table.add_column("When", style="cyan", width=16)
    table.add_column("Kind", style="magenta", width=24)
    table.add_column("Note", style="white")
    for row in rows:
        table.add_row(_relative_time(str(row["occurred_at"])), str(row["kind"]), str(row["note"]))
    console.print(table)


@app.command()
def status() -> None:
    """Show current companion status, mood, and session stats."""
    settings, soul = _bootstrap()
    mood_engine = MoodEngine(settings)
    voice_bridge = VoiceBridge(settings) if settings.enable_voice else None
    telegram_runner = TelegramBotRunner(settings=settings) if settings.enable_telegram else None
    now = runtime_now(settings)
    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)
    total_sessions = messages_repo.count_sessions()
    total_messages = messages_repo.count_messages(role="user")
    presence_context = build_presence_context(settings.database_url, settings, now=now)
    queued_candidates = (
        refresh_proactive_candidates(settings, channel="cli") if settings.enable_proactive else []
    )

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
    table.add_row("Next milestone", _next_milestone_label(settings, total_messages, now=now))
    console.print(table)


@app.command("run-jobs")
def run_jobs() -> None:
    """Run maintenance jobs (consolidation, decay, drift, reflection, proactive)."""
    settings, _ = _bootstrap()
    try:
        results = run_enabled_maintenance(settings)
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


@app.command("telegram-bot")
def telegram_bot() -> None:
    """Start the Telegram bot interface (requires ENABLE_TELEGRAM=true)."""
    settings = get_settings()
    if not settings.enable_telegram:
        console.print("[yellow]Telegram feature is disabled. Set ENABLE_TELEGRAM=true to use this command.[/yellow]")
        raise typer.Exit(code=1)
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
    try:
        runner.run_forever()
    except Exception as exc:
        console.print(f"[red]Telegram bot stopped.[/red] {exc}")
        raise typer.Exit(code=1)


@db_app.callback(invoke_without_command=True)
def db_default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    console.print(ctx.get_help())


@db_app.command("init")
def db_init() -> None:
    """Initialize or migrate the SQLite database schema."""
    settings = get_settings()
    _ensure_runtime_files(settings)
    db.init_db(settings.database_url)
    console.print(f"[green]Initialized database at {settings.redacted_database_url}[/green]")


@db_app.command("rebuild-fts")
def db_rebuild_fts() -> None:
    """Rebuild the SQLite FTS5 memory search index from scratch."""
    settings = get_settings()
    db.rebuild_memory_fts(settings.database_url)
    console.print("[green]FTS5 memory index rebuilt successfully.[/green]")


@debug_app.command("last-turn")
def debug_last_turn() -> None:
    """Show the trace from the most recent conversation turn."""
    settings, _ = _bootstrap()
    trace = TurnTraceRepository(settings.database_url, user_id=settings.user_id).get_last_trace()
    if trace is None:
        console.print("[dim]No turn traces recorded yet.[/dim]")
        return
    console.print_json(json.dumps(trace, indent=2, ensure_ascii=True))


@debug_app.command("show-mood")
def debug_show_mood() -> None:
    """Show the latest mood snapshot for the current user."""
    settings, _ = _bootstrap()
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


@debug_app.command("show-facts")
def debug_show_facts() -> None:
    """Show the raw user story/facts payload as JSON."""
    settings, _ = _bootstrap()
    payload = UserFactsRepository(settings.database_url, user_id=settings.user_id).export_story_payload()
    console.print_json(json.dumps(payload, indent=2, ensure_ascii=True))


@debug_app.command("show-memories")
def debug_show_memories(limit: int = typer.Option(20, min=1, max=200)) -> None:
    """Show top episodic memories with scores and metadata."""
    settings, _ = _bootstrap()
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


@debug_app.command("show-personality")
def debug_show_personality(limit: int = typer.Option(10, min=1, max=100)) -> None:
    """Show personality state history (drift versions)."""
    settings, _ = _bootstrap()
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
        table.add_row(
            str(row.get("version", "")),
            str(row.get("created_at", ""))[:10],
            state_str,
            sig_str,
        )
    console.print(table)


@debug_app.command("show-trace")
def debug_show_trace(trace_id: str = typer.Argument(..., help="Trace ID.")) -> None:
    """Show a specific turn trace by ID."""
    settings, _ = _bootstrap()
    trace = TurnTraceRepository(settings.database_url).get_trace(trace_id)
    if trace is None:
        console.print(f"[red]Trace not found:[/red] {trace_id}")
        raise typer.Exit(code=1)
    console.print_json(json.dumps(trace, indent=2, ensure_ascii=True))


@debug_app.command("explain-memory")
def debug_explain_memory(memory_id: str = typer.Argument(..., help="Memory ID.")) -> None:
    """Show all stored fields for a specific memory by ID."""
    settings, _ = _bootstrap()
    row = EpisodicMemoryRepository(settings=settings).get_row(memory_id)
    if row is None:
        console.print(f"[red]Memory not found:[/red] {memory_id}")
        raise typer.Exit(code=1)
    console.print_json(json.dumps(row, indent=2, ensure_ascii=True))


@app.command()
def config() -> None:
    """Show current configuration (API keys redacted)."""
    settings = get_settings()
    console.print_json(json.dumps(settings.as_redacted_dict(), indent=2))


@app.command()
def version() -> None:
    """Show the installed SOUL version."""
    console.print(f"SOUL {__version__}")


def _conversation_streak_progress(settings: Settings, *, now: datetime) -> int:
    session_days = sorted(
        {
            _parse_iso_datetime(str(session["started_at"])).astimezone(now.tzinfo).date()
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


def _anniversary_progress(settings: Settings, *, days: int, now: datetime) -> int | None:
    sessions = db.list_sessions(settings.database_url, limit=1)
    if not sessions:
        return None
    first_date = _parse_iso_datetime(str(sessions[0]["started_at"])).astimezone(now.tzinfo).date()
    elapsed = (now.date() - first_date).days
    return max(0, days - elapsed)


def _next_milestone_label(settings: Settings, total_messages: int, *, now: datetime | None = None) -> str:
    now = now or runtime_now(settings)
    candidates: list[tuple[int, str, str]] = []

    if total_messages < settings.milestone_message_count and not db.milestone_exists(settings.database_url, "hundredth_message"):
        remaining = max(0, settings.milestone_message_count - total_messages)
        candidates.append(
            (
                3 if remaining > 0 else 0,
                "hundredth_message",
                f"{_message_milestone_label(settings.milestone_message_count)} ({remaining} away)",
            )
        )

    if not db.milestone_exists(settings.database_url, "seven_day_streak"):
        streak = _conversation_streak_progress(settings, now=now)
        remaining = max(0, settings.milestone_streak_days - streak) if streak else settings.milestone_streak_days
        label = (
            f"{settings.milestone_streak_days}-day conversation streak (today)"
            if remaining == 0
            else f"{settings.milestone_streak_days}-day conversation streak ({_format_countdown(remaining, 'day')})"
        )
        candidates.append((remaining, "seven_day_streak", label))

    if not db.milestone_exists(settings.database_url, "one_month_anniversary"):
        remaining = _anniversary_progress(settings, days=settings.milestone_one_month_days, now=now)
        if remaining is not None:
            label = "1-month anniversary (today)" if remaining == 0 else f"1-month anniversary ({_format_countdown(remaining, 'day')})"
            candidates.append((remaining, "one_month_anniversary", label))

    if not db.milestone_exists(settings.database_url, "three_month_anniversary"):
        remaining = _anniversary_progress(settings, days=settings.milestone_three_month_days, now=now)
        if remaining is not None:
            label = "3-month anniversary (today)" if remaining == 0 else f"3-month anniversary ({_format_countdown(remaining, 'day')})"
            candidates.append((remaining, "three_month_anniversary", label))

    if not candidates:
        return "relationship timeline is active"

    _, _, label = min(candidates, key=lambda item: (item[0], item[1]))
    return label


def main() -> None:
    app()


if __name__ == "__main__":
    main()
