from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from soul.config import Settings, get_settings

from .vector_store import MemoryRecord, build_vector_store


class EpisodicMemoryRepository:
    def __init__(self, store_path: str | Path, *, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.store = build_vector_store(store_path, settings=self.settings)

    def add_text(
        self,
        content: str,
        *,
        emotional_tag: str | None = None,
        importance: float = 0.5,
        memory_type: str = "moment",
        metadata: dict[str, str] | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            id=str(uuid4()),
            content=content,
            emotional_tag=emotional_tag,
            importance=importance,
            memory_type=memory_type,
            metadata=metadata or {},
        )
        self.store.add(record)
        return record

    def recent(self, limit: int = 10) -> list[MemoryRecord]:
        return self.store.load_all()[-limit:]

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        return self.store.search(query, limit=limit)

    def clear(self) -> int:
        return self.store.clear()
