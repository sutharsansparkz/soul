from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

from soul import db
from soul.config import Settings, get_settings
from soul.core.llm_client import LLMClient
from soul.core.soul_loader import compile_system_prompt, load_soul
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.user_story import UserStoryRepository
from soul.tasks import celery_app


@dataclass(slots=True)
class ReflectionEntry:
    date: str
    summary: str
    insights: list[str]


class ReflectionRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass

    def load(self) -> list[ReflectionEntry]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [ReflectionEntry(**item) for item in payload]

    def append(self, entry: ReflectionEntry) -> None:
        items = self.load()
        items.append(entry)
        self.path.write_text(json.dumps([asdict(item) for item in items], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass


def generate_monthly_reflection(settings: Settings | None = None) -> ReflectionEntry | None:
    settings = settings or get_settings()
    repo = ReflectionRepository(settings.reflections_file)
    today = datetime.now(timezone.utc).date()
    month_key = today.strftime("%Y-%m")
    if any(item.date.startswith(month_key) for item in repo.load()):
        return None

    story_repo = UserStoryRepository(settings.user_story_file)
    story = story_repo.load()
    soul = load_soul(settings.soul_file)
    client = LLMClient(settings, soul)
    recent_milestones = db.list_milestones(settings.database_url, limit=5)
    recent_memories = db.list_memories(settings.database_url, limit=5)

    prompt = _build_reflection_prompt(story, recent_milestones, recent_memories)
    result = client.complete_text(
        system_prompt=compile_system_prompt(soul)
        + "\n\nWrite a brief self-reflection as the companion. Return strict JSON with keys summary and insights.",
        user_prompt=prompt,
    )

    entry = _parse_reflection_response(result.text) or _fallback_reflection(story, recent_milestones, recent_memories)
    entry.date = today.isoformat()
    repo.append(entry)

    episodic = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    episodic.add_text(
        entry.summary,
        emotional_tag="reflective",
        importance=0.7,
        memory_type="insight",
        metadata={
            "source": "monthly_reflection",
            "date": entry.date,
            "session_id": "monthly-reflection",
            "user_id": settings.user_id,
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        },
    )
    db.save_memory(
        settings.database_url,
        label="monthly reflection",
        content=entry.summary,
        importance=0.7,
        source="reflection",
    )
    return entry


def _build_reflection_prompt(
    story,
    milestones: list[dict[str, object]],
    memories: list[dict[str, object]],
) -> str:
    milestone_text = "\n".join(f"- {item['occurred_at']}: {item['note']}" for item in milestones) or "- none"
    memory_text = "\n".join(f"- {item['label']}: {item['content']}" for item in memories) or "- none"
    story_summary = story.current_chapter.get("summary", "") if story.current_chapter else ""
    return (
        "Reflect on the recent relationship with the user.\n"
        f"Current chapter: {story_summary}\n"
        f"Observed values: {', '.join(story.values_observed) if story.values_observed else 'none'}\n"
        f"Milestones:\n{milestone_text}\n"
        f"Recent memories:\n{memory_text}\n"
        "Return JSON only."
    )


def _parse_reflection_response(text: str) -> ReflectionEntry | None:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        payload = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None

    summary = str(payload.get("summary", "")).strip()
    raw_insights = payload.get("insights", [])
    insights = [str(item).strip() for item in raw_insights if str(item).strip()]
    if not summary:
        return None
    return ReflectionEntry(date="", summary=summary, insights=insights[:5])


def _fallback_reflection(story, milestones, memories) -> ReflectionEntry:
    summary_bits = []
    if story.current_chapter and story.current_chapter.get("summary"):
        summary_bits.append(str(story.current_chapter["summary"]))
    if milestones:
        summary_bits.append(f"Recent milestone: {milestones[-1]['note']}")
    if memories:
        summary_bits.append(f"Memory that lingers: {memories[0]['content']}")
    summary = " ".join(summary_bits)[:320].strip() or "I am still learning the shape of this relationship."
    insights = [
        "The user returns with emotional continuity rather than isolated prompts.",
        "Warmth and specificity matter more than generic reassurance.",
        "Small recurring phrases are becoming part of the relationship.",
    ]
    return ReflectionEntry(date="", summary=summary, insights=insights)


if celery_app is not None:

    @celery_app.task(name="soul.evolution.reflection.monthly_reflection_task")
    def monthly_reflection_task() -> dict[str, object]:
        settings = get_settings()
        db.init_db(settings.database_url)
        entry = generate_monthly_reflection(settings)
        if entry is None:
            return {"created": False}
        return {"created": True, "date": entry.date, "summary": entry.summary}
