from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from soul import db
from soul.cli_support import chat as cli_chat
from soul.cli_support import debug as cli_debug
from soul.cli_support import memories as cli_memories
from soul.cli_support import runtime as cli_runtime
from soul.cli_support import status as cli_status
from soul.cli_support import story as cli_story
from soul.config import Settings, get_settings
from soul.core.llm_client import LLMClient
from soul.core.mood_engine import MoodEngine
from soul.core.presence_context import runtime_now
from soul.core.skill_templates import get_builtin_skill_template, list_builtin_skill_templates, read_builtin_skill_template
from soul.maintenance.jobs import run_enabled_maintenance, trigger_maintenance_if_due
from soul.maintenance.proactive import refresh_proactive_candidates
from soul.presence.telegram import TelegramBotRunner
from soul.presence.voice import VoiceBridge


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


_parse_iso_datetime = cli_status.parse_iso_datetime
_format_countdown = cli_status.format_countdown
_message_milestone_label = cli_status.message_milestone_label
_local_timezone_name = cli_runtime.local_timezone_name
_serialize_env_value = cli_runtime.serialize_env_value
_render_env_content = cli_runtime.render_env_content
_settings_for_init = cli_runtime.settings_for_init
_record_hms_score = cli_memories.record_hms_score
_record_tier = cli_memories.record_tier
_score_bar = cli_memories.score_bar
_record_retrieval_rank = cli_memories.record_retrieval_rank
_simple_similarity = cli_memories.simple_similarity
_clamp01 = cli_memories.clamp01
_normalize_voice_transcript = cli_chat.normalize_voice_transcript
_match_local_runtime_query = cli_chat.match_local_runtime_query
_local_runtime_mood = cli_chat.local_runtime_mood
_refresh_reach_out_candidates = cli_chat.refresh_reach_out_candidates_for_cli
_conversation_streak_progress = cli_status.conversation_streak_progress
_anniversary_progress = cli_status.anniversary_progress


def _relative_time(iso_str: str) -> str:
    return cli_memories.relative_time(iso_str, datetime_module=datetime)


def _mkdir_secure(path: Path) -> None:
    cli_runtime.mkdir_secure(path)


def _write_secure(path: Path, content: str) -> None:
    cli_runtime.write_secure(path, content)


def _ensure_runtime_files(settings: Settings) -> None:
    cli_runtime.ensure_runtime_files(settings)


def _bootstrap():
    return cli_runtime.bootstrap(ensure_runtime_files_func=_ensure_runtime_files)


def _prompt_text(label: str, *, default: str | None = None, required: bool = False) -> str:
    return cli_runtime.prompt_text(console, Prompt.ask, label, default=default, required=required)


def _prompt_secret(label: str, *, existing: str | None = None, required: bool = False) -> str:
    return cli_runtime.prompt_secret(console, Prompt.ask, label, existing=existing, required=required)


def _prompt_timezone(default: str) -> str:
    return cli_runtime.prompt_timezone(console, default, prompt_text_func=_prompt_text)


def _prompt_int(label: str, *, default: str | None = None) -> str:
    return cli_runtime.prompt_int(console, label, default=default, prompt_text_func=_prompt_text)


def _print_header(soul, session_id: str, mood=None) -> None:
    cli_chat.print_header(console, soul, session_id, mood)


def _run_orchestrated_turn(orchestrator, *, soul, session_id: str, user_input: str):
    return cli_chat.run_orchestrated_turn(console, orchestrator, soul=soul, session_id=session_id, user_input=user_input)


def _show_last_session(settings: Settings) -> None:
    cli_chat.show_last_session(console, settings)


def _render_story(settings: Settings) -> None:
    cli_story.render_story(console, settings)


def _show_pending_reach_outs(settings: Settings, soul) -> None:
    cli_chat.show_pending_reach_outs(console, settings, soul)


def _voice_output(voice_bridge, enabled: bool, text: str) -> None:
    cli_chat.voice_output(console, voice_bridge, enabled, text)


def _capture_voice_input(voice_bridge, *, seconds: int) -> str | None:
    return cli_chat.capture_voice_input(
        console,
        voice_bridge,
        seconds=seconds,
        normalize_voice_transcript_func=_normalize_voice_transcript,
    )


def _local_runtime_reply(settings: Settings, *, speaker_name: str, query_kind: str):
    return cli_chat.local_runtime_reply(
        console,
        settings,
        speaker_name=speaker_name,
        query_kind=query_kind,
        runtime_now_func=runtime_now,
    )


def _print_local_runtime_trace(soul, mood, *, query_kind: str) -> None:
    cli_chat.print_local_runtime_trace(console, soul, mood, query_kind=query_kind)


def _handle_session_command(
    raw_input: str,
    *,
    settings: Settings,
    session_id: str,
    current_mood,
    voice_output_enabled: bool,
    voice_chat_mode: bool,
    voice_bridge,
    episodic_repo,
):
    return cli_chat.handle_session_command(
        console,
        raw_input,
        settings=settings,
        session_id=session_id,
        current_mood=current_mood,
        voice_output_enabled=voice_output_enabled,
        voice_chat_mode=voice_chat_mode,
        voice_bridge=voice_bridge,
        episodic_repo=episodic_repo,
        render_story_func=_render_story,
    )


def _next_milestone_label(settings: Settings, total_messages: int, *, now: datetime | None = None) -> str:
    return cli_status.next_milestone_label(settings, total_messages, now=now, runtime_now_func=runtime_now)


@app.command()
def init(
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to the .env file to write."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing .env file without prompting."),
) -> None:
    """Create a local .env and bootstrap the SQLite runtime."""
    cli_runtime.run_init_command(
        console=console,
        env_file=env_file,
        force=force,
        confirm_ask=Confirm.ask,
        prompt_text_func=_prompt_text,
        prompt_secret_func=_prompt_secret,
        prompt_timezone_func=_prompt_timezone,
        prompt_int_func=_prompt_int,
    )


@app.command()
def chat(
    voice: bool = typer.Option(False, "--voice", help="Synthesize assistant replies when configured."),
    replay: bool = typer.Option(False, "--replay", help="Show the previous session before starting."),
    voice_input: Path | None = typer.Option(None, "--voice-input", help="Transcribe an audio file and use it as the first turn."),
    record_seconds: int = typer.Option(0, "--record-seconds", help="Record microphone input before the session when sounddevice is available."),
) -> None:
    """Start an interactive chat session with your AI companion."""
    cli_chat.run_chat_command(
        console=console,
        voice=voice,
        replay=replay,
        voice_input=voice_input,
        record_seconds=record_seconds,
        prompt_ask=Prompt.ask,
        voice_bridge_cls=VoiceBridge,
        bootstrap=_bootstrap,
        refresh_reach_out_candidates_func=_refresh_reach_out_candidates,
        show_last_session_func=_show_last_session,
        print_header_func=_print_header,
        show_pending_reach_outs_func=_show_pending_reach_outs,
        normalize_voice_transcript_func=_normalize_voice_transcript,
        capture_voice_input_func=_capture_voice_input,
        handle_session_command_func=_handle_session_command,
        match_local_runtime_query_func=_match_local_runtime_query,
        local_runtime_mood_func=_local_runtime_mood,
        local_runtime_reply_func=_local_runtime_reply,
        print_local_runtime_trace_func=_print_local_runtime_trace,
        run_orchestrated_turn_func=_run_orchestrated_turn,
        voice_output_func=_voice_output,
        trigger_maintenance_if_due_func=trigger_maintenance_if_due,
    )


@memories_app.callback(invoke_without_command=True)
def memories_list(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    settings, _ = _bootstrap()
    cli_memories.render_memories_overview(console, settings, relative_time_func=_relative_time)


@skills_app.callback(invoke_without_command=True)
def skills_list(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    skill_table = Table(title="Built-in Workspace Skills", box=box.SIMPLE_HEAVY)
    skill_table.add_column("Name", style="cyan", width=20)
    skill_table.add_column("Description", style="white")
    for template in list_builtin_skill_templates():
        skill_table.add_row(template.name, template.description)
    console.print(skill_table)


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
    cli_memories.search_memories(console, settings, query)


@memories_app.command("top")
def memories_top() -> None:
    """Show the top-scoring (most vivid) memories."""
    settings, _ = _bootstrap()
    cli_memories.show_top_memories(console, settings)


@memories_app.command("cold")
def memories_cold() -> None:
    """Show cold (low-score, fading) memories."""
    settings, _ = _bootstrap()
    cli_memories.show_cold_memories(console, settings, relative_time_func=_relative_time)


@memories_app.command("boost")
def memories_boost(query: str = typer.Argument(..., help="Query to match and boost memory.")) -> None:
    """Boost the HMS score of the best-matching memory."""
    settings, _ = _bootstrap()
    cli_memories.boost_memory(console, settings, query)


@memories_app.command("clear")
def memories_clear() -> None:
    """Wipe all stored memories for the current user."""
    settings, _ = _bootstrap()
    confirmed = Confirm.ask("Wipe all stored memories?", default=False)
    if not confirmed:
        console.print("[dim]Cancelled.[/dim]")
        return
    cli_memories.clear_memories(console, settings)


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
    cli_story.edit_story(console, settings, subprocess_module=subprocess)


@app.command()
def drift() -> None:
    """Show personality drift history over time."""
    settings, _ = _bootstrap()
    cli_status.render_drift(console, settings)


@app.command()
def milestones() -> None:
    """Show relationship milestones and timeline."""
    settings, _ = _bootstrap()
    cli_status.render_milestones(console, settings, relative_time_func=_relative_time)


@app.command()
def status() -> None:
    """Show current companion status, mood, and session stats."""
    settings, soul = _bootstrap()
    cli_status.render_status(
        console,
        settings,
        soul,
        next_milestone_label_func=_next_milestone_label,
        runtime_now_func=runtime_now,
        refresh_proactive_candidates_func=refresh_proactive_candidates,
    )


@app.command("run-jobs")
def run_jobs() -> None:
    """Run maintenance jobs (consolidation, decay, drift, reflection, proactive)."""
    settings, _ = _bootstrap()
    cli_status.run_jobs(console, settings, run_enabled_maintenance_func=run_enabled_maintenance)


@app.command("telegram-bot")
def telegram_bot() -> None:
    """Start the Telegram bot interface (requires ENABLE_TELEGRAM=true)."""
    cli_status.run_telegram_bot(console, settings_loader=get_settings, telegram_runner_cls=TelegramBotRunner)


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
    cli_debug.render_last_turn(console, settings)


@debug_app.command("show-mood")
def debug_show_mood() -> None:
    """Show the latest mood snapshot for the current user."""
    settings, _ = _bootstrap()
    cli_debug.render_mood(console, settings)


@debug_app.command("show-facts")
def debug_show_facts() -> None:
    """Show the raw user story/facts payload as JSON."""
    settings, _ = _bootstrap()
    cli_debug.render_facts(console, settings)


@debug_app.command("show-memories")
def debug_show_memories(limit: int = typer.Option(20, min=1, max=200)) -> None:
    """Show top episodic memories with scores and metadata."""
    settings, _ = _bootstrap()
    cli_debug.render_memories(console, settings, limit=limit)


@debug_app.command("show-personality")
def debug_show_personality(limit: int = typer.Option(10, min=1, max=100)) -> None:
    """Show personality state history (drift versions)."""
    settings, _ = _bootstrap()
    cli_debug.render_personality(console, settings, limit=limit)


@debug_app.command("show-trace")
def debug_show_trace(trace_id: str = typer.Argument(..., help="Trace ID.")) -> None:
    """Show a specific turn trace by ID."""
    settings, _ = _bootstrap()
    cli_debug.render_trace(console, settings, trace_id)


@debug_app.command("explain-memory")
def debug_explain_memory(memory_id: str = typer.Argument(..., help="Memory ID.")) -> None:
    """Show all stored fields for a specific memory by ID."""
    settings, _ = _bootstrap()
    cli_debug.render_memory_row(console, settings, memory_id)


@app.command()
def config() -> None:
    """Show current configuration (API keys redacted)."""
    cli_status.render_config(console)


@app.command()
def version() -> None:
    """Show the installed SOUL version."""
    cli_status.render_version(console)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
