from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from soul import db
from soul.config import Settings, get_settings
from soul.memory.embedder import LocalHybridEmbedder
from soul.memory.fts import ensure_fts_index
from soul.memory.retriever import MemoryRetriever
from soul.memory.scorer import boosted_components, initial_components, recompute_components

from .vector_store import MemoryRecord, build_vector_store


class EpisodicMemoryRepository:
    def __init__(self, store_path: str | Path, *, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.embedder = LocalHybridEmbedder(self.settings)
        try:
            ensure_fts_index(self.settings.database_url)
        except Exception:
            pass
        self.store = build_vector_store(store_path, settings=self.settings)
        self.retriever = MemoryRetriever(self.settings, self)

    def add_text(
        self,
        content: str,
        *,
        emotional_tag: str | None = None,
        importance: float = 0.5,
        memory_type: str = "moment",
        metadata: dict[str, object] | None = None,
    ) -> MemoryRecord:
        metadata = dict(metadata or {})
        memory_id = str(metadata.get("memory_id") or uuid4())
        user_id = str(metadata.get("user_id") or self.settings.user_id)
        session_id = str(metadata.get("session_id") or "sessionless")
        timestamp = str(metadata.get("timestamp") or db.utcnow_iso())
        flagged = bool(metadata.get("flagged", False))
        word_count = len(content.split())
        half_life_days = float(getattr(self.settings, "hms_decay_halflife_days", 30.0))
        components = initial_components(
            emotional_tag=emotional_tag,
            memory_timestamp=timestamp,
            word_count=word_count,
            flagged=flagged,
            half_life_days=half_life_days,
        )

        db.create_episodic_memory(
            self.settings.database_url,
            user_id=user_id,
            session_id=session_id,
            content=content,
            timestamp=timestamp,
            emotional_tag=emotional_tag,
            memory_type=memory_type,
            word_count=word_count,
            flagged=flagged,
            ref_count=0,
            tier=components.tier,
            memory_id=memory_id,
        )
        db.upsert_memory_score(
            self.settings.database_url,
            memory_id=memory_id,
            user_id=user_id,
            score_emotional=components.score_emotional,
            score_retrieval=components.score_retrieval,
            score_temporal=components.score_temporal,
            score_flagged=components.score_flagged,
            score_volume=components.score_volume,
            hms_score=components.hms_score,
            decay_rate=components.decay_rate,
        )
        embedding_blob = self.embedder.encode_to_blob(content)
        if embedding_blob is not None:
            db.update_episodic_embedding(self.settings.database_url, memory_id, embedding_blob)

        enriched_metadata = dict(metadata)
        enriched_metadata.update(
            {
                "memory_id": memory_id,
                "session_id": session_id,
                "user_id": user_id,
                "timestamp": timestamp,
                "hms_score": round(components.hms_score, 4),
                "tier": components.tier,
            }
        )
        record = MemoryRecord(
            id=memory_id,
            content=content,
            emotional_tag=emotional_tag,
            importance=importance,
            memory_type=memory_type,
            metadata=enriched_metadata,
        )
        self.store.add(record)
        return record

    def retrieve(self, *, query: str, user_id: str | None = None, k: int | None = None, passive: bool = True) -> list[MemoryRecord]:
        return self.retriever.retrieve(
            query=query,
            user_id=user_id or self.settings.user_id,
            k=k,
            passive=passive,
        )

    def recent(self, limit: int = 10) -> list[MemoryRecord]:
        rows = db.list_top_episodic_memories(
            self.settings.database_url,
            user_id=self.settings.user_id,
            include_cold=True,
            limit=limit,
        )
        if rows:
            return [self._row_to_record(row) for row in rows]
        return self.store.load_all()[-limit:]

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        # Explicit search includes cold memories.
        retrieved = self.retrieve(query=query, user_id=self.settings.user_id, k=limit, passive=False)
        if retrieved:
            return retrieved
        return self.store.search(
            query,
            limit=limit,
            user_id=self.settings.user_id,
        )

    def list_cold(self, limit: int = 50) -> list[MemoryRecord]:
        rows = db.list_cold_memories(self.settings.database_url, user_id=self.settings.user_id, limit=limit)
        return [self._row_to_record(row) for row in rows]

    def list_top(self, limit: int = 10) -> list[MemoryRecord]:
        rows = db.list_top_episodic_memories(
            self.settings.database_url,
            user_id=self.settings.user_id,
            include_cold=True,
            limit=limit,
        )
        return [self._row_to_record(row) for row in rows]

    def boost(self, memory_id: str) -> dict[str, object] | None:
        row = db.get_episodic_memory(self.settings.database_url, memory_id)
        if row is None:
            return None
        score_row = db.get_memory_score(self.settings.database_url, memory_id) or {}
        ref_count = int(row.get("ref_count") or 0)
        half_life_days = float(getattr(self.settings, "hms_decay_halflife_days", 30.0))
        cold_threshold = float(getattr(self.settings, "hms_cold_threshold", 0.05))
        components = boosted_components(
            emotional_tag=str(row.get("emotional_tag") or ""),
            memory_timestamp=str(row.get("timestamp", db.utcnow_iso())),
            word_count=int(row.get("word_count") or len(str(row.get("content", "")).split())),
            ref_count=ref_count,
            half_life_days=half_life_days,
            cold_threshold=cold_threshold,
            score_emotional_override=float(score_row["score_emotional"]) if "score_emotional" in score_row else None,
        )
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        db.update_episodic_memory_fields(
            self.settings.database_url,
            memory_id,
            flagged=True,
            tier=components.tier,
        )
        db.upsert_memory_score(
            self.settings.database_url,
            memory_id=memory_id,
            user_id=str(row.get("user_id", self.settings.user_id)),
            score_emotional=components.score_emotional,
            score_retrieval=components.score_retrieval,
            score_temporal=components.score_temporal,
            score_flagged=components.score_flagged,
            score_volume=components.score_volume,
            hms_score=components.hms_score,
            last_computed=now_iso,
            last_retrieved=score_row.get("last_retrieved"),
            decay_rate=components.decay_rate,
        )
        self.store.update(
            memory_id,
            metadata={
                "hms_score": round(components.hms_score, 4),
                "tier": components.tier,
                "flagged": 1,
                "last_computed": now_iso,
            },
            ref_count=ref_count,
        )
        return db.get_memory_score(self.settings.database_url, memory_id)

    def decay_all(self, *, now: datetime | None = None) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        half_life_days = float(getattr(self.settings, "hms_decay_halflife_days", 30.0))
        cold_threshold = float(getattr(self.settings, "hms_cold_threshold", 0.05))
        rows = db.list_memory_scores_for_decay(self.settings.database_url, user_id=self.settings.user_id)
        updated = 0
        moved_to_cold = 0
        for row in rows:
            memory_id = str(row["id"])
            previous_tier = str(row.get("tier", "present"))
            components = recompute_components(
                emotional_tag=str(row.get("emotional_tag") or ""),
                memory_timestamp=str(row.get("timestamp", db.utcnow_iso())),
                word_count=int(row.get("word_count") or len(str(row.get("content", "")).split())),
                ref_count=int(row.get("ref_count") or 0),
                flagged=bool(int(row.get("flagged") or 0)),
                now=now,
                half_life_days=half_life_days,
                cold_threshold=cold_threshold,
                score_emotional_override=float(row.get("score_emotional", 0.5)),
            )
            now_iso = now.replace(microsecond=0).isoformat()
            db.update_episodic_memory_fields(
                self.settings.database_url,
                memory_id,
                tier=components.tier,
            )
            db.upsert_memory_score(
                self.settings.database_url,
                memory_id=memory_id,
                user_id=str(row.get("user_id", self.settings.user_id)),
                score_emotional=components.score_emotional,
                score_retrieval=components.score_retrieval,
                score_temporal=components.score_temporal,
                score_flagged=components.score_flagged,
                score_volume=components.score_volume,
                hms_score=components.hms_score,
                last_computed=now_iso,
                last_retrieved=row.get("last_retrieved"),
                decay_rate=components.decay_rate,
            )
            self.store.update(
                memory_id,
                metadata={
                    "hms_score": round(components.hms_score, 4),
                    "tier": components.tier,
                    "last_computed": now_iso,
                },
                ref_count=int(row.get("ref_count") or 0),
            )
            updated += 1
            if previous_tier != "cold" and components.tier == "cold":
                moved_to_cold += 1
        return {"updated": updated, "moved_to_cold": moved_to_cold}

    def clear(self) -> int:
        db_deleted = db.delete_episodic_memories(self.settings.database_url)
        vector_deleted = self.store.clear()
        return db_deleted + vector_deleted

    def _row_to_record(self, row: dict[str, object]) -> MemoryRecord:
        memory_id = str(row.get("id", ""))
        return MemoryRecord(
            id=memory_id,
            content=str(row.get("content", "")),
            emotional_tag=str(row.get("emotional_tag") or "") or None,
            memory_type=str(row.get("memory_type", "moment")),
            ref_count=int(row.get("ref_count") or 0),
            metadata={
                "memory_id": memory_id,
                "session_id": str(row.get("session_id", "")),
                "user_id": str(row.get("user_id", "")),
                "timestamp": str(row.get("timestamp", "")),
                "tier": str(row.get("tier", "present")),
                "hms_score": round(float(row.get("hms_score", 0.5)), 4),
                "flagged": int(row.get("flagged") or 0),
            },
            importance=float(row.get("hms_score", 0.5)),
        )
