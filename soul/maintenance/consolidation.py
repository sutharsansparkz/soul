"""Session consolidation backed by SQLite repositories."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from soul.bootstrap.errors import ExtractionValidationError
from soul import db
from soul.config import Settings, get_settings
from soul.core.llm_client import LLMClient
from soul.core.soul_loader import compile_system_prompt, load_soul
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.shared_language import SharedLanguageRepository
from soul.memory.repositories.user_facts import UserFactsRepository
from soul.memory.user_story import BigMoment, apply_story_observations, ensure_story_defaults, infer_mood_trend
from soul.persistence.db import get_engine, utcnow_iso


@dataclass(slots=True)
class ConsolidationResult:
    processed_messages: int
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


def consolidate_pending_sessions(*, database_url: str, settings: Settings | None = None, source: str = "maintenance") -> list[dict[str, object]]:
    resolved_settings = settings or get_settings()
    messages_repo = MessagesRepository(database_url, user_id=resolved_settings.user_id)
    story_repo = UserFactsRepository(database_url, user_id=resolved_settings.user_id)
    shared_repo = SharedLanguageRepository(database_url, user_id=resolved_settings.user_id)
    memory_repo = EpisodicMemoryRepository(settings=resolved_settings)
    results: list[dict[str, object]] = []
    engine = get_engine(database_url)

    for session_id in messages_repo.list_unconsolidated_completed_session_ids():
        rows = messages_repo.get_session_messages(session_id)
        user_lines = [str(row["content"]).strip() for row in rows if str(row.get("role", "")).casefold() == "user" and str(row.get("content", "")).strip()]
        if not user_lines:
            with engine.begin() as connection:
                messages_repo.mark_session_consolidated(session_id, source=source, connection=connection)
            results.append({"session_id": session_id, "processed_messages": len(rows), "memories_added": 0, "story_updated": False, "skipped": True})
            continue

        story = story_repo.load_story()
        update = apply_story_observations(story, user_lines, mood_hint=infer_mood_trend(user_lines[-1]), observed_at=utcnow_iso())
        structured = _extract_structured_insights(user_lines, resolved_settings)
        story_updated = update.changed or _merge_structured_insights(story, structured)
        memories_added = 0
        with engine.begin() as connection:
            story_repo.save_story(story, source="maintenance", connection=connection)

            for line in user_lines:
                importance = _infer_importance(line)
                if importance < 0.55:
                    continue
                memory_repo.add_text(
                    line,
                    emotional_tag=_infer_emotional_tag(line),
                    importance=importance,
                    memory_type="moment" if importance < 0.8 else "milestone",
                    metadata={
                        "source": "consolidation",
                        "session_id": session_id,
                        "user_id": resolved_settings.user_id,
                        "timestamp": utcnow_iso(),
                        "label": "consolidated session memory",
                    },
                    connection=connection,
                )
                memories_added += 1

            for phrase in ("late night coding", "as always", "rough day"):
                if any(phrase in line.casefold() for line in user_lines):
                    shared_repo.register(phrase, connection=connection)
            for phrase in structured.shared_phrases:
                shared_repo.register(phrase, "llm-extracted session phrase", connection=connection)

            messages_repo.mark_session_consolidated(session_id, source=source, connection=connection)
        results.append(
            {
                "session_id": session_id,
                "processed_messages": len(rows),
                "memories_added": memories_added,
                "story_updated": story_updated,
                "skipped": False,
            }
        )
    return results


def _extract_structured_insights(user_lines: list[str], settings: Settings) -> StructuredSessionInsights:
    soul = load_soul(settings.soul_file)
    client = LLMClient(settings, soul)
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
    return _parse_structured_insights(result.text)


def _parse_structured_insights(text: str) -> StructuredSessionInsights:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        payload = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as exc:
        raise ExtractionValidationError(f"Structured insight extraction failed: {text!r}") from exc

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


def _merge_structured_insights(story, insights: StructuredSessionInsights) -> bool:  # type: ignore[no-untyped-def]
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
    known_relationships = {(item["name"], item["role"]) for item in story.relationships}
    for item in insights.relationships:
        key = (item["name"], item["role"])
        if key not in known_relationships:
            story.relationships.append(item)
            known_relationships.add(key)
            changed = True
    known_big_moments = {moment.event for moment in story.big_moments}
    for event in insights.big_moments:
        if event not in known_big_moments:
            story.big_moments.append(
                BigMoment(
                    date=datetime.now(timezone.utc).date().isoformat(),
                    event=event,
                    emotional_weight="high",
                    companion_was_there=True,
                )
            )
            known_big_moments.add(event)
            changed = True
    story.updated_at = utcnow_iso()
    return changed


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
    if any(token in text.casefold() for token in ("quit my job", "got engaged", "got married", "launched", "moved to", "broke up", "investors", "co-founder")):
        importance += 0.25
    return round(min(0.95, importance), 2)


def _clean_optional_string(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def archive_and_purge_old_session_messages(
    *,
    database_url: str,
    archive_dir: Path,
    retention_days: int,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).replace(microsecond=0).isoformat()
    sessions = db.list_completed_sessions_with_messages_before(database_url, ended_before=cutoff)
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived_sessions = 0
    purged_messages = 0
    failed_sessions = 0

    for session in sessions:
        session_id = str(session["id"])
        messages = db.get_session_messages(database_url, session_id)
        payload = "\n".join(json.dumps(message, ensure_ascii=True) for message in messages) + "\n"
        archive_path = archive_dir / f"{session_id}.jsonl"
        try:
            archive_path.write_text(payload, encoding="utf-8")
            try:
                archive_path.chmod(0o600)
            except OSError:
                failed_sessions += 1
                continue
        except Exception:
            failed_sessions += 1
            continue

        archived_sessions += 1
        purged_messages += db.delete_session_messages(database_url, session_id)

    return {
        "archived_sessions": archived_sessions,
        "purged_messages": purged_messages,
        "failed_sessions": failed_sessions,
    }
