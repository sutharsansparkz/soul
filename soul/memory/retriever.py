from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from soul import db
from soul.memory.embedder import LocalHybridEmbedder
from soul.memory.scorer import recompute_components
from soul.memory.vector_store import MemoryRecord


if TYPE_CHECKING:
    from soul.config import Settings
    from soul.memory.episodic import EpisodicMemoryRepository


class MemoryRetriever:
    def __init__(self, settings: "Settings", repository: "EpisodicMemoryRepository"):
        self.settings = settings
        self.repository = repository
        self.embedder = getattr(repository, "embedder", LocalHybridEmbedder(settings))

    def retrieve(
        self,
        *,
        query: str,
        user_id: str,
        k: int | None = None,
        passive: bool = True,
    ) -> list[MemoryRecord]:
        candidate_k = int(getattr(self.settings, "memory_candidate_k", 20))
        top_k = int(k or self.settings.memory_retrieval_k)
        semantic_weight = float(getattr(self.settings, "hms_semantic_weight", 0.55))
        hms_weight = float(getattr(self.settings, "hms_score_weight", 0.45))
        half_life_days = float(getattr(self.settings, "hms_decay_halflife_days", 30.0))
        cold_threshold = float(getattr(self.settings, "hms_cold_threshold", 0.05))

        fts_rows = db.search_episodic_memories_fts(
            self.settings.database_url,
            query,
            user_id=user_id,
            include_cold=not passive,
            limit=candidate_k,
        )
        bm25_similarity = self._normalize_bm25_rows(fts_rows)
        query_embedding = self.embedder.encode(query) if self.embedder.status.enabled else None

        candidates: list[tuple[MemoryRecord, dict[str, object] | None]] = []
        for row in fts_rows:
            record = self._record_from_row(row)
            candidates.append((record, row))

        if not candidates:
            fallback = self.repository.store.search(
                query,
                limit=candidate_k,
                user_id=user_id,
                min_hms_score=(cold_threshold if passive else None),
                exclude_tiers=({"cold"} if passive else None),
            )
            candidates.extend((record, None) for record in fallback)

        ranked: list[tuple[float, MemoryRecord, str]] = []
        for record, row_hint in candidates:
            memory_id = self._resolve_memory_id(record)
            row = db.get_episodic_memory(self.settings.database_url, memory_id)
            if row is None:
                metadata_user_id = str(record.metadata.get("user_id", "")).strip()
                if metadata_user_id and metadata_user_id != user_id:
                    continue
                row = self._backfill_memory_row(
                    record,
                    user_id=metadata_user_id or user_id,
                    memory_id=memory_id,
                )

            row_user_id = str(row.get("user_id", "")).strip()
            if row_user_id and row_user_id != user_id:
                continue

            score_row = db.get_memory_score(self.settings.database_url, memory_id)
            if score_row is None:
                score_row = self._backfill_score_row(
                    row,
                    half_life_days=half_life_days,
                    cold_threshold=cold_threshold,
                )

            tier = str(row.get("tier", "present"))
            if passive and tier == "cold":
                continue

            if row_hint is not None:
                bm25_score = float(row_hint.get("bm25_score", 0.0))
                bm25_component = bm25_similarity.get(memory_id, 0.0)
                semantic_similarity = bm25_component
                record.metadata["bm25_raw"] = f"{bm25_score:.4f}"
                record.metadata["bm25_score"] = f"{bm25_component:.4f}"
                record.metadata["bm25_similarity"] = f"{bm25_component:.4f}"

                candidate_embedding = self.embedder.decode_blob(row_hint.get("embedding"))
                cosine = self.embedder.cosine_similarity(query_embedding, candidate_embedding)
                if query_embedding is not None and candidate_embedding is not None:
                    semantic_similarity = ((bm25_component * 0.35) + (cosine * 0.20)) / 0.55
                    record.metadata["cosine_similarity"] = f"{cosine:.4f}"
            else:
                semantic_similarity = self._semantic_similarity(query, record.content, record=record)
            hms_score = float(score_row.get("hms_score", 0.5))
            retrieval_rank = (semantic_similarity * semantic_weight) + (hms_score * hms_weight)

            record.metadata["memory_id"] = memory_id
            record.metadata["semantic_similarity"] = f"{semantic_similarity:.4f}"
            record.metadata["hms_score"] = f"{hms_score:.4f}"
            record.metadata["tier"] = tier
            record.metadata["retrieval_rank"] = f"{retrieval_rank:.4f}"

            ranked.append((retrieval_rank, record, memory_id))

        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = ranked[:top_k]
        updated: list[MemoryRecord] = []
        for _, record, memory_id in selected:
            self._apply_retrieval_boost(
                memory_id=memory_id,
                half_life_days=half_life_days,
                cold_threshold=cold_threshold,
            )
            refreshed = db.get_memory_score(self.settings.database_url, memory_id) or {}
            refreshed_row = db.get_episodic_memory(self.settings.database_url, memory_id) or {}
            record.metadata["hms_score"] = f"{float(refreshed.get('hms_score', 0.5)):.4f}"
            record.metadata["tier"] = str(refreshed_row.get("tier", "present"))
            updated.append(record)
        return updated

    def _resolve_memory_id(self, record: MemoryRecord) -> str:
        explicit = str(record.metadata.get("memory_id", "")).strip()
        if explicit:
            return explicit
        return record.id

    def _backfill_memory_row(self, record: MemoryRecord, *, user_id: str, memory_id: str) -> dict[str, object]:
        timestamp = str(record.metadata.get("timestamp", "")).strip() or db.utcnow_iso()
        session_id = str(record.metadata.get("session_id", "")).strip() or "legacy"
        db.create_episodic_memory(
            self.settings.database_url,
            user_id=user_id,
            session_id=session_id,
            content=record.content,
            timestamp=timestamp,
            emotional_tag=record.emotional_tag,
            memory_type=record.memory_type,
            word_count=len(record.content.split()),
            flagged=False,
            ref_count=record.ref_count,
            tier="present",
            memory_id=memory_id,
        )
        return db.get_episodic_memory(self.settings.database_url, memory_id) or {
            "id": memory_id,
            "user_id": user_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "content": record.content,
            "emotional_tag": record.emotional_tag,
            "memory_type": record.memory_type,
            "word_count": len(record.content.split()),
            "flagged": 0,
            "ref_count": record.ref_count,
            "tier": "present",
        }

    def _backfill_score_row(
        self,
        memory_row: dict[str, object],
        *,
        half_life_days: float,
        cold_threshold: float,
    ) -> dict[str, object]:
        components = recompute_components(
            emotional_tag=str(memory_row.get("emotional_tag") or ""),
            memory_timestamp=str(memory_row.get("timestamp", db.utcnow_iso())),
            word_count=int(memory_row.get("word_count") or 0),
            ref_count=int(memory_row.get("ref_count") or 0),
            flagged=bool(int(memory_row.get("flagged") or 0)),
            half_life_days=half_life_days,
            cold_threshold=cold_threshold,
        )
        db.upsert_memory_score(
            self.settings.database_url,
            memory_id=str(memory_row["id"]),
            user_id=str(memory_row.get("user_id", self.settings.user_id)),
            score_emotional=components.score_emotional,
            score_retrieval=components.score_retrieval,
            score_temporal=components.score_temporal,
            score_flagged=components.score_flagged,
            score_volume=components.score_volume,
            hms_score=components.hms_score,
            decay_rate=components.decay_rate,
        )
        db.update_episodic_memory_fields(
            self.settings.database_url,
            str(memory_row["id"]),
            tier=components.tier,
        )
        return db.get_memory_score(self.settings.database_url, str(memory_row["id"])) or {
            "hms_score": components.hms_score
        }

    def _apply_retrieval_boost(
        self,
        *,
        memory_id: str,
        half_life_days: float,
        cold_threshold: float,
    ) -> None:
        memory_row = db.get_episodic_memory(self.settings.database_url, memory_id)
        if memory_row is None:
            return
        score_row = db.get_memory_score(self.settings.database_url, memory_id) or {}
        ref_count = int(memory_row.get("ref_count") or 0) + 1
        flagged = bool(int(memory_row.get("flagged") or 0))
        components = recompute_components(
            emotional_tag=str(memory_row.get("emotional_tag") or ""),
            memory_timestamp=str(memory_row.get("timestamp", db.utcnow_iso())),
            word_count=int(memory_row.get("word_count") or len(str(memory_row.get("content", "")).split())),
            ref_count=ref_count,
            flagged=flagged,
            half_life_days=half_life_days,
            cold_threshold=cold_threshold,
            score_emotional_override=float(score_row["score_emotional"]) if "score_emotional" in score_row else None,
        )
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        db.update_episodic_memory_fields(
            self.settings.database_url,
            memory_id,
            ref_count_delta=1,
            tier=components.tier,
        )
        db.upsert_memory_score(
            self.settings.database_url,
            memory_id=memory_id,
            user_id=str(memory_row.get("user_id", self.settings.user_id)),
            score_emotional=components.score_emotional,
            score_retrieval=components.score_retrieval,
            score_temporal=components.score_temporal,
            score_flagged=components.score_flagged,
            score_volume=components.score_volume,
            hms_score=components.hms_score,
            last_computed=now_iso,
            last_retrieved=now_iso,
            decay_rate=components.decay_rate,
        )
        self.repository.store.update(
            memory_id,
            metadata={
                "hms_score": round(components.hms_score, 4),
                "tier": components.tier,
                "last_computed": now_iso,
                "last_retrieved": now_iso,
            },
            ref_count=ref_count,
        )

    def _semantic_similarity(self, query: str, content: str, *, record: MemoryRecord) -> float:
        raw = record.metadata.get("semantic_similarity")
        if raw is not None:
            try:
                return max(0.0, min(1.0, float(raw)))
            except (TypeError, ValueError):
                pass
        query_tokens = {token.casefold() for token in query.split() if token.strip()}
        if not query_tokens:
            return 0.0
        content_tokens = {token.casefold() for token in content.split() if token.strip()}
        overlap = len(query_tokens & content_tokens)
        overlap_score = overlap / max(1, len(query_tokens))
        substring_boost = 0.35 if query.casefold() in content.casefold() else 0.0
        return min(1.0, overlap_score + substring_boost)

    def _normalize_bm25_rows(self, rows: list[dict[str, object]]) -> dict[str, float]:
        scored: list[tuple[str, float]] = []
        for row in rows:
            memory_id = str(row.get("id", ""))
            if not memory_id:
                continue
            try:
                score = float(row.get("bm25_score", 0.0))
            except (TypeError, ValueError):
                continue
            scored.append((memory_id, score))
        if not scored:
            return {}
        values = [item[1] for item in scored]
        lowest = min(values)
        highest = max(values)
        if highest <= lowest:
            return {memory_id: 1.0 for memory_id, _ in scored}
        output: dict[str, float] = {}
        scale = highest - lowest
        for memory_id, value in scored:
            output[memory_id] = max(0.0, min(1.0, 1.0 - ((value - lowest) / scale)))
        return output

    def _record_from_row(self, row: dict[str, object]) -> MemoryRecord:
        memory_id = str(row.get("id", ""))
        return MemoryRecord(
            id=memory_id,
            content=str(row.get("content", "")),
            emotional_tag=str(row.get("emotional_tag") or "") or None,
            memory_type=str(row.get("memory_type", "moment")),
            ref_count=int(row.get("ref_count") or 0),
            importance=float(row.get("hms_score", 0.5)),
            metadata={
                "memory_id": memory_id,
                "session_id": str(row.get("session_id", "")),
                "user_id": str(row.get("user_id", "")),
                "timestamp": str(row.get("timestamp", "")),
                "tier": str(row.get("tier", "present")),
                "hms_score": round(float(row.get("hms_score", 0.5)), 4),
                "flagged": int(row.get("flagged") or 0),
            },
        )
