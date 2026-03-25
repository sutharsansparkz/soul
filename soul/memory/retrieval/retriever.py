"""SQLite-backed memory retrieval with hybrid semantic + BM25 ranking."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from soul.memory.embedder import LocalHybridEmbedder
from soul.memory.vector_store import MemoryRecord

if TYPE_CHECKING:
    from soul.config import Settings
    from soul.memory.repositories.episodic import EpisodicMemoryRepository

_logger = logging.getLogger(__name__)


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
        mutate_on_retrieve: bool = True,
    ) -> list[MemoryRecord]:
        candidate_k = int(getattr(self.settings, "memory_candidate_k", 20))
        top_k = int(k or self.settings.memory_retrieval_k)

        rows = self.repository.search_candidates(
            query,
            user_id=user_id,
            include_cold=not passive,
            limit=candidate_k,
        )
        bm25_similarity = self._normalize_bm25_rows(rows)
        query_embedding = self.embedder.encode(query) if self.embedder.status.enabled else None

        # Dynamic weights: when embeddings are available, lean toward semantic
        # similarity; otherwise fall back to BM25-only with HMS score.
        if query_embedding is not None:
            semantic_weight = float(getattr(self.settings, "hms_semantic_weight", 0.55))
            hms_weight = float(getattr(self.settings, "hms_score_weight", 0.45))
        else:
            semantic_weight = 0.40
            hms_weight = 0.60

        ranked: list[tuple[float, MemoryRecord]] = []
        for row in rows:
            tier = str(row.get("tier", "present"))
            if passive and tier == "cold":
                continue
            record = self.repository.row_to_record(row)
            memory_id = str(row.get("id", record.id))
            bm25_component = bm25_similarity.get(memory_id, 0.0)
            semantic_similarity = bm25_component

            try:
                bm25_raw = float(row.get("bm25_score", 0.0))
            except (TypeError, ValueError):
                bm25_raw = 0.0

            candidate_embedding = self.embedder.decode_blob(row.get("embedding"))
            if query_embedding is not None and candidate_embedding is not None:
                cosine = self.embedder.cosine_similarity(query_embedding, candidate_embedding)
                # Weighted fusion: cosine dominates when available
                semantic_similarity = (cosine * 0.70) + (bm25_component * 0.30)
                record.metadata["cosine_similarity"] = f"{cosine:.4f}"

            hms_score = float(row.get("hms_score", 0.5))

            # Dynamic HMS weight boost: vivid and flagged memories get extra weight
            adjusted_hms_weight = hms_weight
            if tier == "vivid" or int(row.get("flagged", 0)):
                adjusted_hms_weight = min(1.0, hms_weight + 0.10)
                semantic_weight_adj = max(0.0, 1.0 - adjusted_hms_weight)
            else:
                semantic_weight_adj = semantic_weight

            # Recency bonus: slight boost for memories observed within the last 7 days
            recency_bonus = self._recency_bonus(str(row.get("observed_at", "")))

            retrieval_rank = (
                (semantic_similarity * semantic_weight_adj)
                + (hms_score * adjusted_hms_weight)
                + recency_bonus
            )

            record.metadata["memory_id"] = memory_id
            record.metadata["bm25_raw"] = f"{bm25_raw:.4f}"
            record.metadata["bm25_score"] = f"{bm25_component:.4f}"
            record.metadata["bm25_similarity"] = f"{bm25_component:.4f}"
            record.metadata["semantic_similarity"] = f"{semantic_similarity:.4f}"
            record.metadata["hms_score"] = f"{hms_score:.4f}"
            record.metadata["tier"] = tier
            record.metadata["retrieval_rank"] = f"{retrieval_rank:.4f}"
            ranked.append((retrieval_rank, record))

        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = [record for _, record in ranked[:top_k]]
        if mutate_on_retrieve:
            for record in selected:
                self._apply_retrieval_boost(record)
                refreshed = self.repository.get_row(str(record.metadata.get("memory_id", record.id)))
                if refreshed is not None:
                    record.metadata["hms_score"] = f"{float(refreshed.get('hms_score', 0.5)):.4f}"
                    record.metadata["tier"] = str(refreshed.get("tier", "present"))
        return selected

    def _apply_retrieval_boost(self, record: MemoryRecord) -> None:
        self.repository.apply_retrieval_boost(str(record.metadata.get("memory_id", record.id)))

    def _recency_bonus(self, observed_at: str) -> float:
        """Small bonus for memories created in the last 7 days."""
        if not observed_at:
            return 0.0
        try:
            from datetime import datetime, timezone

            dt = datetime.fromisoformat(observed_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
            if age_days <= 0:
                return 0.05
            if age_days <= 7:
                return round(0.05 * math.exp(-age_days / 7), 4)
            return 0.0
        except (ValueError, TypeError):
            return 0.0

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
