"""Monthly reflection generation without fallback behavior."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from soul.bootstrap.errors import ExtractionValidationError
from soul.config import Settings, get_settings
from soul.core.llm_client import LLMClient
from soul.core.soul_loader import compile_system_prompt, load_soul
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.milestones import MilestonesRepository
from soul.memory.repositories.reflections import ReflectionArtifact, ReflectionArtifactsRepository
from soul.memory.repositories.user_facts import UserFactsRepository


def generate_monthly_reflection(settings: Settings | None = None) -> ReflectionArtifact | None:
    settings = settings or get_settings()
    repo = ReflectionArtifactsRepository(settings.database_url, user_id=settings.user_id)
    today = datetime.now(timezone.utc).date()
    month_key = today.strftime("%Y-%m")
    if repo.get_by_key(month_key) is not None:
        return None

    story = UserFactsRepository(settings.database_url, user_id=settings.user_id).load_story()
    milestones = MilestonesRepository(settings.database_url).list(limit=settings.reflection_recent_items_limit)
    memories = EpisodicMemoryRepository(settings=settings).list_top(limit=settings.reflection_recent_items_limit)
    soul = load_soul(settings.soul_file)
    client = LLMClient(settings, soul)

    prompt = _build_reflection_prompt(story, milestones, memories)
    result = client.complete_text(
        system_prompt=(
            compile_system_prompt(soul)
            + "\n\nWrite a brief self-reflection as the companion. Return strict JSON with keys summary and insights."
        ),
        user_prompt=prompt,
    )
    entry = _parse_reflection_response(result.text)
    entry.date = month_key
    repo.append(entry, source="maintenance")
    EpisodicMemoryRepository(settings=settings).add_text(
        entry.summary,
        emotional_tag="reflective",
        importance=settings.reflection_memory_importance,
        memory_type="insight",
        metadata={
            "source": "monthly_reflection",
            "date": entry.date,
            "session_id": "monthly-reflection",
            "user_id": settings.user_id,
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "label": "monthly reflection",
        },
    )
    return entry


def _build_reflection_prompt(story, milestones: list[dict[str, object]], memories) -> str:  # type: ignore[no-untyped-def]
    milestone_text = "\n".join(f"- {item['occurred_at']}: {item['note']}" for item in milestones) or "- none"
    memory_text = "\n".join(f"- [{item.emotional_tag or 'unknown'}] {item.content}" for item in memories) or "- none"
    story_summary = story.current_chapter.get("summary", "") if story.current_chapter else ""
    return (
        "Reflect on the recent relationship with the user.\n"
        f"Current chapter: {story_summary}\n"
        f"Observed values: {', '.join(story.values_observed) if story.values_observed else 'none'}\n"
        f"Milestones:\n{milestone_text}\n"
        f"Episodic memories (vivid):\n{memory_text}\n"
        "Return JSON only."
    )


def _parse_reflection_response(text: str) -> ReflectionArtifact:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        payload = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as exc:
        raise ExtractionValidationError(f"Reflection response was not valid JSON: {text!r}") from exc
    summary = str(payload.get("summary", "")).strip()
    raw_insights = payload.get("insights", [])
    insights = [str(item).strip() for item in raw_insights if str(item).strip()]
    if not summary or not isinstance(raw_insights, list):
        raise ExtractionValidationError("Reflection response is missing required summary/insights fields.")
    return ReflectionArtifact(date="", summary=summary, insights=insights[:5])
