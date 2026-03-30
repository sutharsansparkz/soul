from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Callable

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from soul import db
from soul.bootstrap import TurnExecutionError
from soul.config import Settings
from soul.conversation.orchestrator import ConversationOrchestrator
from soul.core.llm_client import LLMResult
from soul.core.mood_engine import MoodSnapshot
from soul.core.presence_context import runtime_now
from soul.core.soul_loader import Soul
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.mood import MoodSnapshotsRepository
from soul.memory.repositories.proactive import ProactiveCandidateRepository
from soul.observability.traces import TurnTraceRepository
from soul.presence.voice import VoiceBridge
from soul.maintenance.jobs import trigger_maintenance_if_due
from soul.maintenance.proactive import refresh_proactive_candidates


def print_header(console: Console, soul: Soul, session_id: str, mood: MoodSnapshot | None = None) -> None:
    status = f"{soul.name} - session {session_id[:8]} - /quit to exit"
    if mood:
        status = f"{status} - mood: {mood.companion_state}"
    console.print()
    console.print(Panel(status, box=box.SIMPLE, border_style="magenta"))


def render_static_reply(
    console: Console,
    *,
    speaker_name: str,
    text: str,
    provider: str,
    model: str,
) -> LLMResult:
    console.print(f"[bold magenta]{speaker_name}[/bold magenta] > {text}")
    return LLMResult(text=text, provider=provider, model=model, fallback_used=False)


def print_turn_trace(console: Console, soul: Soul, mood: MoodSnapshot, bundle: object) -> None:
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


def run_orchestrated_turn(
    console: Console,
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
        print_turn_trace(console, soul, mood, bundle)

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


def show_last_session(console: Console, settings: Settings) -> None:
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


def refresh_reach_out_candidates_for_cli(settings: Settings) -> None:
    if not settings.enable_proactive:
        return
    refresh_proactive_candidates(settings, channel="cli")


def show_pending_reach_outs(console: Console, settings: Settings, soul: Soul) -> None:
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


def voice_output(console: Console, voice_bridge: VoiceBridge, enabled: bool, text: str) -> None:
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


def normalize_voice_transcript(text: str) -> str:
    normalized = text.strip()
    lowered = normalized.casefold()
    if lowered in {"quit", "exit", "goodbye", "stop"}:
        return "/quit"
    if lowered in {"show mood", "what is my mood"}:
        return "/mood"
    return normalized


def capture_voice_input(
    console: Console,
    voice_bridge: VoiceBridge,
    *,
    seconds: int,
    normalize_voice_transcript_func: Callable[[str], str] = normalize_voice_transcript,
) -> str | None:
    recording = voice_bridge.record_to_file(seconds=seconds)
    if not recording.ok or not recording.output_path:
        console.print(f"[yellow]voice recording unavailable: {recording.error}[/yellow]")
        return None

    transcript = voice_bridge.transcribe(recording.output_path)
    if not transcript.ok or not transcript.text:
        console.print(f"[yellow]voice transcription unavailable: {transcript.error}[/yellow]")
        return None

    console.print(f"[dim]recorded and transcribed voice input from {recording.output_path}[/dim]")
    return normalize_voice_transcript_func(transcript.text)


def match_local_runtime_query(text: str) -> str | None:
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


def local_runtime_mood(query_kind: str) -> MoodSnapshot:
    return MoodSnapshot(
        user_mood="curious",
        companion_state="curious",
        confidence=1.0,
        rationale=f"local runtime {query_kind} query",
    )


def local_runtime_reply(
    console: Console,
    settings: Settings,
    *,
    speaker_name: str,
    query_kind: str,
    runtime_now_func: Callable[..., object] = runtime_now,
) -> LLMResult:
    local_now = runtime_now_func(settings)
    timezone_label = getattr(local_now.tzinfo, "key", None) or local_now.tzname() or settings.timezone_name
    clock_label = local_now.strftime("%I:%M %p").lstrip("0")
    date_label = local_now.strftime("%A, %B %d, %Y")
    text = f"It's {clock_label} on {date_label} ({timezone_label})."
    return render_static_reply(
        console,
        speaker_name=speaker_name,
        text=text,
        provider="local-runtime",
        model=f"runtime-{query_kind}",
    )


def print_local_runtime_trace(console: Console, soul: Soul, mood: MoodSnapshot, *, query_kind: str) -> None:
    console.print(
        f"[dim]inside {soul.name}[/dim] "
        f"[magenta]{mood.companion_state}[/magenta] "
        f"[dim](user: {mood.user_mood}, local: {query_kind})[/dim]"
    )
    console.print(f"[dim]{soul.name} is checking the local {query_kind}...[/dim]")


def handle_session_command(
    console: Console,
    raw_input: str,
    *,
    settings: Settings,
    session_id: str,
    current_mood: MoodSnapshot | None,
    voice_output_enabled: bool,
    voice_chat_mode: bool,
    voice_bridge: VoiceBridge,
    episodic_repo: EpisodicMemoryRepository,
    render_story_func: Callable[[Settings], None],
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
        render_story_func(settings)
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
        score = (
            float(boosted["hms_score"])
            if boosted and "hms_score" in boosted
            else float(saved.metadata.get("hms_score", 0.5))
        )
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


def run_chat_command(
    *,
    console: Console,
    voice: bool,
    replay: bool,
    voice_input: Path | None,
    record_seconds: int,
    prompt_ask: Callable[..., str],
    voice_bridge_cls,
    bootstrap: Callable[[], tuple[Settings, Soul]],
    refresh_reach_out_candidates_func: Callable[[Settings], None],
    show_last_session_func: Callable[[Settings], None],
    print_header_func: Callable[[Soul, str, MoodSnapshot | None], None],
    show_pending_reach_outs_func: Callable[[Settings, Soul], None],
    normalize_voice_transcript_func: Callable[[str], str],
    capture_voice_input_func: Callable[..., str | None],
    handle_session_command_func: Callable[..., tuple[bool, bool, bool]],
    match_local_runtime_query_func: Callable[[str], str | None],
    local_runtime_mood_func: Callable[[str], MoodSnapshot],
    local_runtime_reply_func: Callable[..., LLMResult],
    print_local_runtime_trace_func: Callable[..., None],
    run_orchestrated_turn_func: Callable[..., tuple[object, MoodSnapshot]],
    voice_output_func: Callable[[VoiceBridge, bool, str], None],
    trigger_maintenance_if_due_func: Callable[[Settings], None],
) -> None:
    settings, soul = bootstrap()
    if voice and not settings.enable_voice:
        console.print("[yellow]Voice feature is disabled. Set ENABLE_VOICE=true to use --voice.[/yellow]")
        raise typer.Exit(code=1)
    if (voice_input or record_seconds > 0) and not settings.enable_voice:
        console.print("[yellow]Voice feature is disabled. Set ENABLE_VOICE=true to use voice input.[/yellow]")
        raise typer.Exit(code=1)
    refresh_reach_out_candidates_func(settings)
    if replay:
        show_last_session_func(settings)

    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)
    trace_repo = TurnTraceRepository(settings.database_url, user_id=settings.user_id)
    session_id = messages_repo.create_session(soul.name)
    orchestrator = ConversationOrchestrator(settings, soul)
    mood_repo = MoodSnapshotsRepository(settings.database_url, user_id=settings.user_id)
    voice_bridge = voice_bridge_cls(settings)
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
            pending_inputs.append(normalize_voice_transcript_func(transcript.text))
            console.print(f"[dim]loaded voice input from {voice_input}[/dim]")
        else:
            console.print(f"[yellow]voice transcription unavailable: {transcript.error}[/yellow]")
    elif record_seconds > 0:
        captured = capture_voice_input_func(voice_bridge, seconds=voice_record_seconds)
        if captured:
            pending_inputs.append(captured)

    try:
        print_header_func(soul, session_id)
        show_pending_reach_outs_func(settings, soul)
        while True:
            if pending_inputs:
                user_input = pending_inputs.pop(0)
                console.print(f"[bold cyan]You[/bold cyan]: {user_input}")
            else:
                try:
                    if voice_chat_mode:
                        typed_or_blank = prompt_ask("[bold cyan]You[/bold cyan] (Enter=record)", default="").strip()
                        if typed_or_blank:
                            user_input = typed_or_blank
                        else:
                            captured = capture_voice_input_func(voice_bridge, seconds=voice_record_seconds)
                            if captured:
                                user_input = captured
                                console.print(f"[bold cyan]You[/bold cyan]: {user_input}")
                            else:
                                user_input = prompt_ask("[bold cyan]You[/bold cyan] (typed fallback)", default="").strip()
                    else:
                        user_input = prompt_ask("[bold cyan]You[/bold cyan]").strip()
                except (KeyboardInterrupt, EOFError):
                    console.print()
                    break

            if not user_input:
                continue

            if user_input.startswith("/"):
                should_quit, updated_voice_output, updated_voice_chat_mode = handle_session_command_func(
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

            runtime_query = match_local_runtime_query_func(user_input)
            if runtime_query is not None:
                current_mood = local_runtime_mood_func(runtime_query)

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
                print_local_runtime_trace_func(soul, current_mood, query_kind=runtime_query)
                result = local_runtime_reply_func(settings, speaker_name=soul.name, query_kind=runtime_query)
                voice_output_func(voice_bridge, voice_output_enabled, result.text)
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
                    turn_result, current_mood = run_orchestrated_turn_func(
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
                voice_output_func(voice_bridge, voice_output_enabled, result.text)
            console.print(f"[dim]-- {soul.name}: {current_mood.companion_state} | you: {current_mood.user_mood} --[/dim]")
    finally:
        messages_repo.close_session(session_id)
        orchestrator.post_processor.process_session_end(session_id=session_id)
        orchestrator.shutdown()
        trigger_maintenance_if_due_func(settings)
