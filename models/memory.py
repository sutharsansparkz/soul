from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Memory:
    id: str
    user_id: str
    session_id: str
    timestamp: str
    content: str
    emotional_tag: str | None = None
    importance: float = 0.5
    memory_type: str = "moment"
    ref_count: int = 0

