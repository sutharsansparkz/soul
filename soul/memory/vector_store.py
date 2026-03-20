from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Protocol
import json
import math

from soul.config import Settings


@dataclass(slots=True)
class MemoryRecord:
    id: str
    content: str
    emotional_tag: str | None = None
    importance: float = 0.5
    memory_type: str = "moment"
    ref_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


class MemoryStore(Protocol):
    def add(self, record: MemoryRecord) -> None: ...

    def load_all(self) -> list[MemoryRecord]: ...

    def search(
        self,
        query: str,
        limit: int = 5,
        *,
        user_id: str | None = None,
        min_hms_score: float | None = None,
        include_tiers: set[str] | None = None,
        exclude_tiers: set[str] | None = None,
    ) -> list[MemoryRecord]: ...

    def clear(self) -> int: ...

    def update(self, memory_id: str, *, metadata: dict[str, object], ref_count: int | None = None) -> None: ...


class LocalVectorStore:
    """Stable lexical fallback that works without external services."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
            self.path.chmod(0o600)
        except OSError:
            pass

    def add(self, record: MemoryRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=True) + "\n")

    def load_all(self) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        if not self.path.exists():
            return records
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                records.append(MemoryRecord(**payload))
        return records

    def search(
        self,
        query: str,
        limit: int = 5,
        *,
        user_id: str | None = None,
        min_hms_score: float | None = None,
        include_tiers: set[str] | None = None,
        exclude_tiers: set[str] | None = None,
    ) -> list[MemoryRecord]:
        tokens = {token.lower() for token in query.split() if token}
        scored: list[tuple[float, MemoryRecord]] = []
        for record in self.load_all():
            if not _matches_filters(
                record,
                user_id=user_id,
                min_hms_score=min_hms_score,
                include_tiers=include_tiers,
                exclude_tiers=exclude_tiers,
            ):
                continue
            text_tokens = {token.lower() for token in record.content.split() if token}
            overlap = len(tokens & text_tokens)
            similarity = overlap / max(1, len(tokens) if tokens else 1)
            score = overlap + record.importance + math.log1p(record.ref_count)
            if query.lower() in record.content.lower():
                score += 2.0
                similarity = min(1.0, similarity + 0.35)
            record.metadata["semantic_similarity"] = round(min(1.0, similarity), 4)
            scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored[:limit]]

    def clear(self) -> int:
        existing = self.load_all()
        self.path.write_text("", encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        return len(existing)

    def update(self, memory_id: str, *, metadata: dict[str, object], ref_count: int | None = None) -> None:
        records = self.load_all()
        changed = False
        for record in records:
            if record.id != memory_id:
                continue
            record.metadata.update(metadata)
            if ref_count is not None:
                record.ref_count = int(ref_count)
            changed = True
            break
        if not changed:
            return
        with self.path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(asdict(record), ensure_ascii=True) + "\n")


def build_vector_store(path: str | Path, settings: Settings | None = None) -> LocalVectorStore:
    return LocalVectorStore(path)


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _matches_filters(
    record: MemoryRecord,
    *,
    user_id: str | None,
    min_hms_score: float | None,
    include_tiers: set[str] | None,
    exclude_tiers: set[str] | None,
) -> bool:
    if user_id:
        record_user_id = str(record.metadata.get("user_id", "")).strip()
        if record_user_id and record_user_id != user_id:
            return False
    hms_score = _as_float(record.metadata.get("hms_score", record.importance), default=record.importance)
    if min_hms_score is not None and hms_score < min_hms_score:
        return False
    tier = str(record.metadata.get("tier", "")).strip().casefold()
    if include_tiers:
        normalized = {value.casefold() for value in include_tiers}
        if tier and tier not in normalized:
            return False
    if exclude_tiers:
        normalized = {value.casefold() for value in exclude_tiers}
        if tier and tier in normalized:
            return False
    return True


def format_memory_blocks(memories: Iterable[MemoryRecord]) -> list[str]:
    blocks = []
    for memory in memories:
        prefix = memory.memory_type
        if memory.emotional_tag:
            prefix = f"{prefix}:{memory.emotional_tag}"
        blocks.append(f"[memory:{prefix}] {memory.content}")
    return blocks
