from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Protocol
import json
import math

from soul.config import Settings, get_settings


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

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]: ...

    def clear(self) -> int: ...

    def update(self, memory_id: str, *, metadata: dict[str, object], ref_count: int | None = None) -> None: ...


class LocalVectorStore:
    """Stable lexical fallback that works without external services."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

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

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        tokens = {token.lower() for token in query.split() if token}
        scored: list[tuple[float, MemoryRecord]] = []
        for record in self.load_all():
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


class ChromaVectorStore:
    """Optional Chroma-backed memory store for production deployments."""

    def __init__(self, settings: Settings, collection_name: str = "episodic_memory"):
        self.settings = settings
        self.collection_name = collection_name
        self.client = None
        self.collection = self._build_collection()

    def add(self, record: MemoryRecord) -> None:
        if self.collection is None:
            return
        metadata = {
            "emotional_tag": record.emotional_tag or "",
            "importance": float(record.importance),
            "memory_type": record.memory_type,
            "ref_count": int(record.ref_count),
        }
        metadata.update(record.metadata)
        try:
            self.collection.add(
                ids=[record.id],
                documents=[record.content],
                metadatas=[metadata],
            )
        except Exception:
            try:
                self.collection.upsert(
                    ids=[record.id],
                    documents=[record.content],
                    metadatas=[metadata],
                )
            except Exception:
                return

    def load_all(self) -> list[MemoryRecord]:
        if self.collection is None:
            return []
        try:
            payload = self.collection.get(include=["documents", "metadatas"])
        except Exception:
            return []

        documents = payload.get("documents") or []
        metadatas = payload.get("metadatas") or []
        ids = payload.get("ids") or []
        records: list[MemoryRecord] = []
        for record_id, content, metadata in zip(ids, documents, metadatas):
            metadata = metadata or {}
            records.append(
                MemoryRecord(
                    id=str(record_id),
                    content=str(content),
                    emotional_tag=str(metadata.get("emotional_tag") or "") or None,
                    importance=float(metadata.get("importance", 0.5)),
                    memory_type=str(metadata.get("memory_type", "moment")),
                    ref_count=int(metadata.get("ref_count", 0)),
                    metadata={key: value for key, value in metadata.items() if key not in {"emotional_tag", "importance", "memory_type", "ref_count"}},
                )
            )
        return records

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        if self.collection is None:
            return []
        try:
            payload = self.collection.query(
                query_texts=[query],
                n_results=limit,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

        documents = (payload.get("documents") or [[]])[0]
        metadatas = (payload.get("metadatas") or [[]])[0]
        ids = (payload.get("ids") or [[]])[0]
        distances = (payload.get("distances") or [[]])[0]
        records: list[MemoryRecord] = []
        for record_id, content, metadata, distance in zip(ids, documents, metadatas, distances):
            metadata = metadata or {}
            similarity = 1.0 / (1.0 + float(distance or 0.0))
            metadata = dict(metadata)
            metadata["semantic_similarity"] = round(similarity, 4)
            records.append(
                MemoryRecord(
                    id=str(record_id),
                    content=str(content),
                    emotional_tag=str(metadata.get("emotional_tag") or "") or None,
                    importance=float(metadata.get("importance", 0.5)),
                    memory_type=str(metadata.get("memory_type", "moment")),
                    ref_count=int(metadata.get("ref_count", 0)),
                    metadata={key: value for key, value in metadata.items() if key not in {"emotional_tag", "importance", "memory_type", "ref_count"}},
                )
            )
        return records

    def clear(self) -> int:
        if self.collection is None:
            return 0
        try:
            payload = self.collection.get()
            ids = payload.get("ids") or []
            if not ids:
                return 0
            self.collection.delete(ids=ids)
            return len(ids)
        except Exception:
            return 0

    def update(self, memory_id: str, *, metadata: dict[str, object], ref_count: int | None = None) -> None:
        if self.collection is None:
            return
        try:
            row = self.collection.get(ids=[memory_id], include=["metadatas"])
        except Exception:
            return
        metadatas = row.get("metadatas") or []
        if not metadatas:
            return
        merged = dict(metadatas[0] or {})
        merged.update(metadata)
        if ref_count is not None:
            merged["ref_count"] = int(ref_count)
        try:
            self.collection.update(ids=[memory_id], metadatas=[merged])
        except Exception:
            return

    def _build_collection(self):
        try:
            import chromadb
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction, OpenAIEmbeddingFunction
        except ImportError:
            return None

        try:
            if self.settings.chroma_host:
                host, _, port = self.settings.chroma_host.partition(":")
                client = chromadb.HttpClient(host=host, port=int(port or "8000"))
            else:
                client = chromadb.PersistentClient(path=str(self.settings.chroma_dir))
            self.client = client

            embedding_function = None
            if self.settings.openai_api_key:
                embedding_function = OpenAIEmbeddingFunction(
                    api_key=self.settings.openai_api_key,
                    model_name=self.settings.embedding_model,
                )
            else:
                try:
                    embedding_function = DefaultEmbeddingFunction()
                except Exception:
                    embedding_function = None

            return client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=embedding_function,
            )
        except Exception:
            return None


class HybridVectorStore:
    def __init__(self, local_store: LocalVectorStore, chroma_store: ChromaVectorStore | None = None):
        self.local_store = local_store
        self.chroma_store = chroma_store

    def add(self, record: MemoryRecord) -> None:
        self.local_store.add(record)
        if self.chroma_store is not None:
            self.chroma_store.add(record)

    def load_all(self) -> list[MemoryRecord]:
        records = self.local_store.load_all()
        if records:
            return records
        if self.chroma_store is not None:
            return self.chroma_store.load_all()
        return []

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        if self.chroma_store is not None:
            records = self.chroma_store.search(query, limit=limit)
            if records:
                return records
        return self.local_store.search(query, limit=limit)

    def clear(self) -> int:
        deleted = self.local_store.clear()
        if self.chroma_store is not None:
            deleted += self.chroma_store.clear()
        return deleted

    def update(self, memory_id: str, *, metadata: dict[str, object], ref_count: int | None = None) -> None:
        self.local_store.update(memory_id, metadata=metadata, ref_count=ref_count)
        if self.chroma_store is not None:
            self.chroma_store.update(memory_id, metadata=metadata, ref_count=ref_count)


def build_vector_store(path: str | Path, settings: Settings | None = None) -> HybridVectorStore:
    resolved_settings = settings or get_settings()
    local = LocalVectorStore(path)
    chroma = None
    if resolved_settings.chroma_enabled:
        chroma = ChromaVectorStore(resolved_settings)
        if chroma.collection is None:
            chroma = None
    return HybridVectorStore(local_store=local, chroma_store=chroma)


def format_memory_blocks(memories: Iterable[MemoryRecord]) -> list[str]:
    blocks = []
    for memory in memories:
        prefix = memory.memory_type
        if memory.emotional_tag:
            prefix = f"{prefix}:{memory.emotional_tag}"
        blocks.append(f"[memory:{prefix}] {memory.content}")
    return blocks
