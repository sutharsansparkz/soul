"""SQLite-only episodic memory repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.config import Settings, get_settings
from soul.memory.embedder import LocalHybridEmbedder
from soul.memory.retrieval.retriever import MemoryRetriever
from soul.memory.scorer import boosted_components, initial_components, recompute_components
from soul.memory.vector_store import MemoryRecord
from soul.persistence.db import connect, get_engine, utcnow_iso
from soul.persistence.sqlite_setup import ensure_schema


class EpisodicMemoryRepository:
    def __init__(self, *, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.database = self.settings.database_url
        ensure_schema(self.database)
        self.user_id = self.settings.user_id
        self.embedder = LocalHybridEmbedder(self.settings)
        self.retriever = MemoryRetriever(self.settings, self)

    def add_text(
        self,
        content: str,
        *,
        emotional_tag: str | None = None,
        importance: float = 0.5,
        memory_type: str = "moment",
        metadata: dict[str, object] | None = None,
        connection=None,  # type: ignore[no-untyped-def]
    ) -> MemoryRecord:
        metadata = dict(metadata or {})
        memory_id = str(metadata.get("memory_id") or uuid4())
        session_id = str(metadata.get("session_id") or "")
        user_id = str(metadata.get("user_id") or self.user_id)
        observed_at = str(metadata.get("timestamp") or utcnow_iso())
        created_at = utcnow_iso()
        flagged = bool(metadata.get("flagged", False))
        ref_count = int(metadata.get("ref_count") or 0)
        source = str(metadata.get("source") or "auto")
        label = str(metadata.get("label") or "")
        word_count = len(content.split())
        score_override = importance if importance != 0.5 else None
        components = initial_components(
            emotional_tag=emotional_tag,
            memory_timestamp=observed_at,
            word_count=word_count,
            flagged=flagged,
            half_life_days=float(self.settings.hms_decay_halflife_days),
            score_emotional_override=score_override,
        )
        embedding_blob = self.embedder.encode_to_blob(content)
        payload = {
            "id": memory_id,
            "user_id": user_id,
            "session_id": session_id or None,
            "label": label,
            "content": content,
            "emotional_tag": emotional_tag,
            "memory_type": memory_type,
            "source": source,
            "created_at": created_at,
            "updated_at": created_at,
            "observed_at": observed_at,
            "word_count": word_count,
            "flagged": 1 if flagged else 0,
            "ref_count": ref_count,
            "tier": components.tier,
            "score_emotional": components.score_emotional,
            "score_retrieval": components.score_retrieval,
            "score_temporal": components.score_temporal,
            "score_flagged": components.score_flagged,
            "score_volume": components.score_volume,
            "hms_score": components.hms_score,
            "last_computed": created_at,
            "last_retrieved": None,
            "decay_rate": components.decay_rate,
            "embedding": embedding_blob,
            "metadata_json": json.dumps(metadata, ensure_ascii=True),
        }
        try:
            if connection is None:
                with get_engine(self.database).begin() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO episodic_memories (
                                id, user_id, session_id, label, content, emotional_tag, memory_type, source,
                                created_at, updated_at, observed_at, word_count, flagged, ref_count, tier,
                                score_emotional, score_retrieval, score_temporal, score_flagged, score_volume,
                                hms_score, last_computed, last_retrieved, decay_rate, embedding, metadata_json
                            )
                            VALUES (
                                :id, :user_id, :session_id, :label, :content, :emotional_tag, :memory_type, :source,
                                :created_at, :updated_at, :observed_at, :word_count, :flagged, :ref_count, :tier,
                                :score_emotional, :score_retrieval, :score_temporal, :score_flagged, :score_volume,
                                :hms_score, :last_computed, :last_retrieved, :decay_rate, :embedding, :metadata_json
                            )
                            """
                        ),
                        payload,
                    )
            else:
                connection.execute(
                    text(
                        """
                        INSERT INTO episodic_memories (
                            id, user_id, session_id, label, content, emotional_tag, memory_type, source,
                            created_at, updated_at, observed_at, word_count, flagged, ref_count, tier,
                            score_emotional, score_retrieval, score_temporal, score_flagged, score_volume,
                            hms_score, last_computed, last_retrieved, decay_rate, embedding, metadata_json
                        )
                        VALUES (
                            :id, :user_id, :session_id, :label, :content, :emotional_tag, :memory_type, :source,
                            :created_at, :updated_at, :observed_at, :word_count, :flagged, :ref_count, :tier,
                            :score_emotional, :score_retrieval, :score_temporal, :score_flagged, :score_volume,
                            :hms_score, :last_computed, :last_retrieved, :decay_rate, :embedding, :metadata_json
                        )
                        """
                    ),
                    payload,
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return self.row_to_record(payload)

    def retrieve(
        self,
        *,
        query: str,
        user_id: str | None = None,
        k: int | None = None,
        passive: bool = True,
        mutate_on_retrieve: bool = True,
    ) -> list[MemoryRecord]:
        return self.retriever.retrieve(
            query=query,
            user_id=user_id or self.user_id,
            k=k,
            passive=passive,
            mutate_on_retrieve=mutate_on_retrieve,
        )

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        return self.retrieve(query=query, user_id=self.user_id, k=limit, passive=False)

    def recent(self, limit: int = 10) -> list[MemoryRecord]:
        rows = self._fetch_rows(
            """
            SELECT *
            FROM episodic_memories
            WHERE user_id = :user_id
            ORDER BY observed_at DESC
            LIMIT :limit
            """,
            {"user_id": self.user_id, "limit": limit},
        )
        return [self.row_to_record(row) for row in rows]

    def list_top(self, limit: int = 10) -> list[MemoryRecord]:
        rows = self._fetch_rows(
            """
            SELECT *
            FROM episodic_memories
            WHERE user_id = :user_id
            ORDER BY hms_score DESC, observed_at DESC
            LIMIT :limit
            """,
            {"user_id": self.user_id, "limit": limit},
        )
        return [self.row_to_record(row) for row in rows]

    def list_cold(self, limit: int = 50) -> list[MemoryRecord]:
        rows = self._fetch_rows(
            """
            SELECT *
            FROM episodic_memories
            WHERE user_id = :user_id AND tier = 'cold'
            ORDER BY observed_at DESC
            LIMIT :limit
            """,
            {"user_id": self.user_id, "limit": limit},
        )
        return [self.row_to_record(row) for row in rows]

    def boost(self, memory_id: str) -> dict[str, object] | None:
        row = self.get_row(memory_id)
        if row is None:
            return None
        ref_count = int(row.get("ref_count") or 0) + 1
        components = boosted_components(
            emotional_tag=str(row.get("emotional_tag") or ""),
            memory_timestamp=str(row.get("observed_at") or utcnow_iso()),
            word_count=int(row.get("word_count") or len(str(row.get("content", "")).split())),
            ref_count=ref_count,
            half_life_days=float(self.settings.hms_decay_halflife_days),
            cold_threshold=float(self.settings.hms_cold_threshold),
            score_emotional_override=float(row.get("score_emotional", 0.5)),
        )
        now_iso = utcnow_iso()
        self._update_memory(
            memory_id,
            {
                "flagged": 1,
                "ref_count": ref_count,
                "tier": components.tier,
                "score_emotional": components.score_emotional,
                "score_retrieval": components.score_retrieval,
                "score_temporal": components.score_temporal,
                "score_flagged": components.score_flagged,
                "score_volume": components.score_volume,
                "hms_score": components.hms_score,
                "last_computed": now_iso,
                "decay_rate": components.decay_rate,
                "updated_at": now_iso,
            },
        )
        return self.get_row(memory_id)

    def apply_retrieval_boost(self, memory_id: str) -> None:
        row = self.get_row(memory_id)
        if row is None:
            return
        ref_count = int(row.get("ref_count") or 0) + 1
        components = recompute_components(
            emotional_tag=str(row.get("emotional_tag") or ""),
            memory_timestamp=str(row.get("observed_at") or utcnow_iso()),
            word_count=int(row.get("word_count") or len(str(row.get("content", "")).split())),
            ref_count=ref_count,
            flagged=bool(int(row.get("flagged") or 0)),
            half_life_days=float(self.settings.hms_decay_halflife_days),
            cold_threshold=float(self.settings.hms_cold_threshold),
            score_emotional_override=float(row.get("score_emotional", 0.5)),
        )
        now_iso = utcnow_iso()
        self._update_memory(
            memory_id,
            {
                "ref_count": ref_count,
                "tier": components.tier,
                "score_emotional": components.score_emotional,
                "score_retrieval": components.score_retrieval,
                "score_temporal": components.score_temporal,
                "score_flagged": components.score_flagged,
                "score_volume": components.score_volume,
                "hms_score": components.hms_score,
                "last_computed": now_iso,
                "last_retrieved": now_iso,
                "decay_rate": components.decay_rate,
                "updated_at": now_iso,
            },
        )

    def decay_all(self, *, now: datetime | None = None) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        updated = 0
        moved_to_cold = 0
        for row in self._fetch_rows(
            "SELECT * FROM episodic_memories WHERE user_id = :user_id",
            {"user_id": self.user_id},
        ):
            previous_tier = str(row.get("tier") or "present")
            components = recompute_components(
                emotional_tag=str(row.get("emotional_tag") or ""),
                memory_timestamp=str(row.get("observed_at") or utcnow_iso()),
                word_count=int(row.get("word_count") or len(str(row.get("content", "")).split())),
                ref_count=int(row.get("ref_count") or 0),
                flagged=bool(int(row.get("flagged") or 0)),
                now=now,
                half_life_days=float(self.settings.hms_decay_halflife_days),
                cold_threshold=float(self.settings.hms_cold_threshold),
                score_emotional_override=float(row.get("score_emotional", 0.5)),
            )
            now_iso = now.replace(microsecond=0).isoformat()
            self._update_memory(
                str(row["id"]),
                {
                    "tier": components.tier,
                    "score_emotional": components.score_emotional,
                    "score_retrieval": components.score_retrieval,
                    "score_temporal": components.score_temporal,
                    "score_flagged": components.score_flagged,
                    "score_volume": components.score_volume,
                    "hms_score": components.hms_score,
                    "last_computed": now_iso,
                    "decay_rate": components.decay_rate,
                    "updated_at": now_iso,
                },
            )
            updated += 1
            if previous_tier != "cold" and components.tier == "cold":
                moved_to_cold += 1
        return {"updated": updated, "moved_to_cold": moved_to_cold}

    def clear(self) -> int:
        try:
            with get_engine(self.database).begin() as connection:
                result = connection.execute(
                    text("DELETE FROM episodic_memories WHERE user_id = :user_id"),
                    {"user_id": self.user_id},
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return int(result.rowcount or 0)

    def search_candidates(
        self,
        query: str,
        *,
        user_id: str,
        include_cold: bool,
        limit: int,
    ) -> list[dict[str, object]]:
        tokens = [token.strip() for token in query.split() if token.strip()]
        if not tokens:
            return []
        sanitized_tokens = [token.replace('"', "").strip() for token in tokens]
        fts_query = " OR ".join(f'"{token}"' for token in sanitized_tokens if token)
        if not fts_query:
            return []
        filters = ["m.user_id = :user_id"]
        params: dict[str, object] = {"query": fts_query, "limit": limit, "user_id": user_id}
        if not include_cold:
            filters.append("m.tier != 'cold'")
        where_sql = " AND ".join(filters)
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        f"""
                        SELECT m.*, bm25(episodic_memories_fts) AS bm25_score
                        FROM episodic_memories_fts
                        JOIN episodic_memories m ON m.rowid = episodic_memories_fts.rowid
                        WHERE episodic_memories_fts MATCH :query
                          AND {where_sql}
                        ORDER BY bm25(episodic_memories_fts)
                        LIMIT :limit
                        """
                    ),
                    params,
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [dict(row) for row in rows]

    def get_row(self, memory_id: str) -> dict[str, object] | None:
        rows = self._fetch_rows(
            "SELECT * FROM episodic_memories WHERE id = :id LIMIT 1",
            {"id": memory_id},
        )
        return rows[0] if rows else None

    def row_to_record(self, row: dict[str, object]) -> MemoryRecord:
        metadata = json.loads(str(row.get("metadata_json") or "{}"))
        metadata.update(
            {
                "memory_id": str(row.get("id", "")),
                "session_id": str(row.get("session_id") or ""),
                "user_id": str(row.get("user_id") or ""),
                "timestamp": str(row.get("observed_at") or ""),
                "tier": str(row.get("tier", "present")),
                "hms_score": round(float(row.get("hms_score", 0.5)), 4),
                "flagged": int(row.get("flagged") or 0),
                "label": str(row.get("label") or ""),
                "source": str(row.get("source") or ""),
            }
        )
        return MemoryRecord(
            id=str(row.get("id", "")),
            content=str(row.get("content", "")),
            emotional_tag=str(row.get("emotional_tag") or "") or None,
            memory_type=str(row.get("memory_type") or "moment"),
            ref_count=int(row.get("ref_count") or 0),
            importance=float(row.get("hms_score", 0.5)),
            metadata=metadata,
        )

    def _fetch_rows(self, statement: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        try:
            with connect(self.database) as connection:
                rows = connection.execute(text(statement), params or {}).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [dict(row) for row in rows]

    def _update_memory(self, memory_id: str, fields: dict[str, object]) -> None:
        assignments = ", ".join(f"{key} = :{key}" for key in fields)
        params = dict(fields)
        params["id"] = memory_id
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(f"UPDATE episodic_memories SET {assignments} WHERE id = :id"),
                    params,
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
