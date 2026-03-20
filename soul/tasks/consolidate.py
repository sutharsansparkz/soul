from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from soul import db
from soul.config import Settings, get_settings
from soul.core.llm_client import LLMClient
from soul.core.soul_loader import compile_system_prompt, load_soul
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.shared_language import SharedLanguageStore
from soul.memory.user_story import BigMoment, UserStoryRepository, apply_story_observations, ensure_story_defaults, infer_mood_trend
from soul.tasks import celery_app

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ConsolidationResult:
    processed_messages: int
    story_path: str
    memory_path: str
    memories_added: int
    story_updated: bool
    skipped: bool = False


@dataclass(slots=True)
class StructuredSessionInsights:
    summary: str | None = None
    current_mood_trend: str | None = None
    active_goals: list[str] = field(default_factory=list)
    active_fears: list[str] = field(default_factory=list)
    values_observed: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    things_they_love: list[str] = field(default_factory=list)
    relationships: list[dict[str, str]] = field(default_factory=list)
    shared_phrases: list[str] = field(default_factory=list)
    big_moments: list[str] = field(default_factory=list)


def consolidate_day(
    session_log: str | Path,
    story_path: str | Path,
    memory_path: str | Path,
    shared_language_path: str | Path | None = None,
    *,
    dedupe_key: str | None = None,
    ledger_path: str | Path | None = None,
    settings: Settings | None = None,
) -> ConsolidationResult:
    session_path = Path(session_log)
    lines = session_path.read_text(encoding="utf-8").splitlines() if session_path.exists() else []
    return consolidate_lines(
        lines,
        story_path=story_path,
        memory_path=memory_path,
        shared_language_path=shared_language_path,
        dedupe_key=dedupe_key,
        ledger_path=ledger_path,
        settings=settings,
    )


def consolidate_lines(
    lines: list[str],
    *,
    story_path: str | Path,
    memory_path: str | Path,
    shared_language_path: str | Path | None = None,
    dedupe_key: str | None = None,
    ledger_path: str | Path | None = None,
    settings: Settings | None = None,
) -> ConsolidationResult:
    resolved_settings = settings or get_settings()
    ledger = _load_ledger(ledger_path)
    if dedupe_key and ledger.get(dedupe_key):
        return ConsolidationResult(
            processed_messages=len(lines),
            story_path=str(Path(story_path)),
            memory_path=str(Path(memory_path)),
            memories_added=0,
            story_updated=False,
            skipped=True,
        )

    user_lines = _extract_user_lines(lines)
    memory_repo = EpisodicMemoryRepository(memory_path, settings=resolved_settings)
    memories_added = 0
    for line in user_lines:
        if not line.strip():
            continue
        importance = _infer_importance(line)
        if importance < 0.55:
            continue
        memory_repo.add_text(
            line.strip(),
            emotional_tag=_infer_emotional_tag(line),
            importance=importance,
            memory_type="moment" if importance < 0.8 else "milestone",
            metadata={
                "source_key": dedupe_key or "",
                "session_id": dedupe_key or "consolidation",
                "user_id": resolved_settings.user_id,
                "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
        )
        memories_added += 1

    story_repo = UserStoryRepository(story_path)
    story = story_repo.load()
    resolved_user_id = resolved_settings.user_id
    if not story.user_id or story.user_id in ("unknown", ""):
        story.user_id = resolved_user_id
    story_updated = False
    llm_insights: StructuredSessionInsights | None = None
    if user_lines:
        update = apply_story_observations(
            story,
            user_lines,
            mood_hint=infer_mood_trend(user_lines[-1]),
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        story_updated = update.changed
        llm_insights = _extract_structured_insights(user_lines, resolved_settings)
        if llm_insights is None and not (resolved_settings.anthropic_api_key or resolved_settings.openai_api_key):
            warnings.warn(
                "No LLM API keys configured — story consolidation using heuristics only. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY for richer profile extraction.",
                stacklevel=2,
            )
        if llm_insights is not None:
            story_updated = _merge_structured_insights(story, llm_insights) or story_updated
        story_repo.save(story)

    if shared_language_path:
        shared_store = SharedLanguageStore(shared_language_path)
        for phrase in ("late night coding", "as always", "rough day"):
            if any(phrase in line.casefold() for line in user_lines):
                shared_store.register(phrase)
        if llm_insights is not None:
            for phrase in llm_insights.shared_phrases:
                shared_store.register(phrase, "llm-extracted session phrase")

    if dedupe_key and ledger_path:
        ledger[dedupe_key] = {
            "processed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "processed_messages": len(lines),
        }
        _save_ledger(ledger_path, ledger)

    return ConsolidationResult(
        processed_messages=len(lines),
        story_path=str(Path(story_path)),
        memory_path=str(Path(memory_path)),
        memories_added=memories_added,
        story_updated=story_updated,
        skipped=False,
    )


def consolidate_pending_sessions(
    *,
    database_url: str,
    story_path: str | Path,
    memory_path: str | Path,
    shared_language_path: str | Path | None = None,
    ledger_path: str | Path | None = None,
    source: str = "nightly",
    settings: Settings | None = None,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for session_id in db.list_unconsolidated_completed_session_ids(database_url):
        rows = db.get_session_messages(database_url, session_id)
        lines = [f"{row['role']}: {row['content']}" for row in rows]
        result = consolidate_lines(
            lines,
            story_path=story_path,
            memory_path=memory_path,
            shared_language_path=shared_language_path,
            dedupe_key=session_id,
            ledger_path=ledger_path,
            settings=settings,
        )
        db.mark_session_consolidated(database_url, session_id, source=source)
        results.append(
            {
                "session_id": session_id,
                "processed_messages": result.processed_messages,
                "memories_added": result.memories_added,
                "story_updated": result.story_updated,
                "skipped": result.skipped,
            }
        )
    return results


def _load_ledger(path: str | Path | None) -> dict[str, object]:
    if path is None:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_ledger(path: str | Path, payload: dict[str, object]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    try:
        file_path.chmod(0o600)
    except OSError:
        pass


def _extract_user_lines(lines: list[str]) -> list[str]:
    user_lines: list[str] = []
    for line in lines:
        lowered = line.casefold()
        if lowered.startswith("user:") or lowered.startswith("you:"):
            user_lines.append(line.split(":", maxsplit=1)[-1].strip())
    if not user_lines and any(line.strip() for line in lines):
        warnings.warn(
            "No user:/you: prefixes found in consolidation input; skipping memory extraction.",
            stacklevel=2,
        )
    return user_lines


def _infer_emotional_tag(text: str) -> str | None:
    lowered = text.casefold()
    if any(token in lowered for token in ("stress", "panic", "worried", "pressure")):
        return "stressed"
    if any(token in lowered for token in ("rough", "hurt", "alone", "invisible", "sad")):
        return "venting"
    if any(token in lowered for token in ("excited", "won", "happy", "launched", "celebrate")):
        return "celebrating"
    if any(token in lowered for token in ("meaning", "wondering", "thinking about")):
        return "reflective"
    return None


def _infer_importance(text: str) -> float:
    importance = 0.4
    if len(text.split()) >= 12:
        importance += 0.15
    if _infer_emotional_tag(text):
        importance += 0.15
    if _looks_like_big_moment(text):
        importance += 0.25
    return round(min(0.95, importance), 2)


def _looks_like_big_moment(text: str) -> bool:
    lowered = text.casefold()
    return any(
        token in lowered
        for token in (
            "quit my job",
            "got engaged",
            "got married",
            "launched",
            "moved to",
            "broke up",
            "investors",
            "co-founder",
        )
    )


def _extract_structured_insights(user_lines: list[str], settings: Settings) -> StructuredSessionInsights | None:
    if not (settings.anthropic_api_key or settings.openai_api_key):
        return None

    try:
        soul = load_soul(settings.soul_file)
        client = LLMClient(settings, soul)
    except Exception:
        return None

    try:
        result = client.complete_text(
            system_prompt=(
                compile_system_prompt(soul)
                + "\n\nYou are extracting durable relational-memory updates from a completed SOUL conversation."
                + " Return strict JSON only."
            ),
            user_prompt=(
                "Extract stable updates from this session transcript.\n"
                "Return JSON with keys: summary, current_mood_trend, active_goals, active_fears, "
                "values_observed, triggers, things_they_love, relationships, shared_phrases, big_moments.\n"
                "Use arrays for list fields. relationships should be objects with name, role, notes.\n\n"
                + "\n".join(f"- {line}" for line in user_lines)
            ),
        )
        if result.provider == "offline":
            return None
        return _parse_structured_insights(result.text)
    except Exception as exc:
        logger.warning("Structured insight extraction failed: %s", exc, exc_info=True)
        return None


def _parse_structured_insights(text: str) -> StructuredSessionInsights | None:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        payload = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None

    relationships = []
    for item in payload.get("relationships", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        role = str(item.get("role", "")).strip()
        notes = str(item.get("notes", "")).strip()
        if name and role:
            relationships.append({"name": name, "role": role, "notes": notes})

    return StructuredSessionInsights(
        summary=_clean_optional_string(payload.get("summary")),
        current_mood_trend=_clean_optional_string(payload.get("current_mood_trend")),
        active_goals=_clean_string_list(payload.get("active_goals")),
        active_fears=_clean_string_list(payload.get("active_fears")),
        values_observed=_clean_string_list(payload.get("values_observed")),
        triggers=_clean_string_list(payload.get("triggers")),
        things_they_love=_clean_string_list(payload.get("things_they_love")),
        relationships=relationships,
        shared_phrases=_clean_string_list(payload.get("shared_phrases")),
        big_moments=_clean_string_list(payload.get("big_moments")),
    )


def _merge_structured_insights(story, insights: StructuredSessionInsights) -> bool:
    ensure_story_defaults(story)
    changed = False

    if insights.summary and story.current_chapter.get("summary") != insights.summary:
        story.current_chapter["summary"] = insights.summary
        changed = True
    if insights.current_mood_trend and story.current_chapter.get("current_mood_trend") != insights.current_mood_trend:
        story.current_chapter["current_mood_trend"] = insights.current_mood_trend
        changed = True

    for value in insights.active_goals:
        if value not in story.current_chapter["active_goals"]:
            story.current_chapter["active_goals"].append(value)
            changed = True
    for value in insights.active_fears:
        if value not in story.current_chapter["active_fears"]:
            story.current_chapter["active_fears"].append(value)
            changed = True
    for value in insights.values_observed:
        if value not in story.values_observed:
            story.values_observed.append(value)
            changed = True
    for value in insights.triggers:
        if value not in story.triggers:
            story.triggers.append(value)
            changed = True
    for value in insights.things_they_love:
        if value not in story.things_they_love:
            story.things_they_love.append(value)
            changed = True

    known_relationships = {
        (str(item.get("name", "")).casefold(), str(item.get("role", "")).casefold()) for item in story.relationships
    }
    for item in insights.relationships:
        key = (item["name"].casefold(), item["role"].casefold())
        if key not in known_relationships:
            story.relationships.append(item)
            known_relationships.add(key)
            changed = True

    known_events = {moment.event for moment in story.big_moments}
    for event in insights.big_moments:
        truncated = event[:180]
        if truncated and truncated not in known_events:
            story.big_moments.append(
                BigMoment(
                    date=datetime.now(timezone.utc).date().isoformat(),
                    event=truncated,
                    emotional_weight="high",
                    companion_was_there=True,
                )
            )
            known_events.add(truncated)
            changed = True

    return changed


def _clean_optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _clean_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in items:
            items.append(text)
    return items


def archive_and_purge_old_session_messages(
    *,
    database_url: str,
    archive_dir: str | Path,
    retention_days: int = 90,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).replace(microsecond=0).isoformat()
    sessions = db.list_completed_sessions_with_messages_before(database_url, ended_before=cutoff)
    archive_path = Path(archive_dir)
    archive_path.mkdir(parents=True, exist_ok=True)
    try:
        archive_path.chmod(0o700)
    except OSError as exc:
        warnings.warn(f"Could not secure archive directory {archive_path}: {exc}", stacklevel=2)

    archived_sessions = 0
    purged_messages = 0
    failed_sessions = 0
    for row in sessions:
        session_id = str(row["id"])
        messages = db.get_session_messages(database_url, session_id)
        if not messages:
            continue
        payload = [
            {
                "session_id": session_id,
                "started_at": row.get("started_at"),
                "ended_at": row.get("ended_at"),
                "role": message.get("role"),
                "content": message.get("content"),
                "created_at": message.get("created_at"),
                "user_mood": message.get("user_mood"),
                "companion_state": message.get("companion_state"),
                "provider": message.get("provider"),
                "metadata_json": message.get("metadata_json"),
            }
            for message in messages
        ]
        file_path = archive_path / f"{session_id}.jsonl"
        try:
            file_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=True) for item in payload) + ("\n" if payload else ""),
                encoding="utf-8",
            )
        except Exception:
            failed_sessions += 1
            continue

        try:
            file_path.chmod(0o600)
        except OSError as exc:
            failed_sessions += 1
            warnings.warn(
                f"Could not secure archive file {file_path}: {exc} - skipping purge for session {session_id}",
                stacklevel=2,
            )
            continue

        try:
            deleted = db.delete_session_messages(database_url, session_id)
        except Exception:
            failed_sessions += 1
            continue
        purged_messages += deleted
        archived_sessions += 1
    return {
        "archived_sessions": archived_sessions,
        "purged_messages": purged_messages,
        "failed_sessions": failed_sessions,
    }


if celery_app is not None:

    @celery_app.task(name="soul.tasks.consolidate.nightly_consolidation_task")
    def nightly_consolidation_task() -> dict[str, object]:
        settings = get_settings()
        db.init_db(settings.database_url)
        results = consolidate_pending_sessions(
            database_url=settings.database_url,
            story_path=settings.user_story_file,
            memory_path=settings.episodic_memory_file,
            shared_language_path=settings.shared_language_file,
            ledger_path=settings.consolidation_ledger_file,
            source="nightly",
            settings=settings,
        )
        archive = archive_and_purge_old_session_messages(
            database_url=settings.database_url,
            archive_dir=settings.session_archive_dir,
            retention_days=settings.raw_retention_days,
        )
        return {"sessions": results, "count": len(results), "archive": archive}
