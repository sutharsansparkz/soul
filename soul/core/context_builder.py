from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from soul import db
from soul.config import Settings
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul, compile_system_prompt
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.user_story import UserStoryRepository
from soul.memory.vector_store import format_memory_blocks


@dataclass(slots=True)
class ContextBundle:
    system_prompt: str
    messages: list[dict[str, str]]
    story_summary: str | None
    memory_snippets: list[str]


class ContextBuilder:
    def __init__(self, settings: Settings, soul: Soul) -> None:
        self.settings = settings
        self.soul = soul
        self.story_repo = UserStoryRepository(settings.user_story_file)
        self.episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)

    def build(self, *, session_id: str, user_input: str, mood: MoodSnapshot) -> ContextBundle:
        recent_messages = db.get_recent_session_messages(self.settings.database_url, session_id, limit=12)
        story_summary = self._story_summary()
        memory_snippets = self._memory_context(user_input)

        system_parts = [
            f"[user_mood: {mood.user_mood}]",
            f"[companion_state: {mood.companion_state}]",
            "Read the emotional context before you answer.",
            "",
            compile_system_prompt(self.soul),
        ]
        if story_summary:
            system_parts.extend(["", "[user_story]", story_summary])
        if memory_snippets:
            system_parts.extend(["", "[memory_context]"])
            system_parts.extend(memory_snippets)

        messages = [{"role": row["role"], "content": str(row["content"])} for row in recent_messages]
        messages.append({"role": "user", "content": user_input})

        return ContextBundle(
            system_prompt="\n".join(system_parts).strip(),
            messages=messages,
            story_summary=story_summary,
            memory_snippets=memory_snippets,
        )

    def _story_summary(self) -> str | None:
        story = self.story_repo.load()
        parts: list[str] = []
        if story.basics:
            bits = ", ".join(f"{key}: {value}" for key, value in story.basics.items() if value)
            if bits:
                parts.append(f"Basics: {bits}")
        if story.current_chapter:
            summary = story.current_chapter.get("summary")
            if summary:
                parts.append(f"Current chapter: {summary}")
            mood = story.current_chapter.get("current_mood_trend")
            if mood:
                parts.append(f"Mood trend: {mood}")
        if story.values_observed:
            parts.append(f"Observed values: {', '.join(story.values_observed)}")
        if story.things_they_love:
            parts.append(f"Things they love: {', '.join(story.things_they_love)}")
        return "\n".join(parts) if parts else None

    def _memory_context(self, query: str) -> list[str]:
        query_limit = 8
        episodic = self.episodic_repo.search(query, limit=query_limit)
        manual = db.search_memories(self.settings.database_url, query=query, limit=query_limit)
        ranked = self._rank_memories(query=query, episodic=episodic, manual=manual)
        if not ranked:
            return []
        top_n = min(5, len(ranked))
        if len(ranked) >= 3:
            top_n = max(3, top_n)
        return [item["block"] for item in ranked[:top_n]]

    def _rank_memories(
        self,
        *,
        query: str,
        episodic,
        manual: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        query_tokens = {token.casefold() for token in query.split() if token.strip()}
        candidates: list[dict[str, object]] = []

        for memory in episodic:
            timestamp = memory.metadata.get("timestamp") or memory.metadata.get("created_at")
            block = format_memory_blocks([memory])[0]
            candidates.append(
                {
                    "block": block,
                    "text": memory.content,
                    "importance": float(memory.importance),
                    "timestamp": str(timestamp) if timestamp else None,
                }
            )

        for row in manual:
            content = str(row.get("content", ""))
            label = str(row.get("label", "memory"))
            candidates.append(
                {
                    "block": f"[memory:manual] {label}: {content}",
                    "text": content,
                    "importance": float(row.get("importance", 0.5)),
                    "timestamp": str(row.get("created_at", "")) or None,
                }
            )

        scored: list[tuple[float, dict[str, object]]] = []
        for candidate in candidates:
            text = str(candidate["text"])
            text_tokens = {token.casefold() for token in text.split() if token.strip()}
            overlap = len(query_tokens & text_tokens)
            overlap_score = overlap / max(1, len(query_tokens))
            substring_boost = 0.3 if query.casefold() in text.casefold() else 0.0
            relevance = overlap_score + substring_boost
            recency = self._recency_score(candidate.get("timestamp"))
            importance = float(candidate["importance"])
            score = (1.8 * relevance) + (0.8 * importance) + (0.6 * recency)
            scored.append((score, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in scored]

    def _recency_score(self, raw_timestamp: object) -> float:
        if raw_timestamp is None:
            return 0.2
        try:
            parsed = datetime.fromisoformat(str(raw_timestamp))
        except ValueError:
            return 0.2
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86_400)
        return 1.0 / (1.0 + (age_days / 30.0))
