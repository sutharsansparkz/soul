from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime, timezone

from rich import box
from rich.console import Console
from rich.table import Table

from soul.config import Settings
from soul.memory.repositories.user_facts import UserFactsRepository


def render_story(console: Console, settings: Settings) -> None:
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


def edit_story(console: Console, settings: Settings, *, subprocess_module=subprocess) -> None:
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
        subprocess_module.run(command, check=False)
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
