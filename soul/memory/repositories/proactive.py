"""Repository for proactive candidates and delivery state."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import connect, get_engine, utcnow_iso


class ProactiveCandidateRepository:
    def __init__(self, database: str | Path, *, user_id: str = "local-user"):
        self.database = database
        self.user_id = user_id

    def replace_pending(self, candidates: list[dict[str, object]], *, channel: str = "cli") -> None:
        now_iso = utcnow_iso()
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        DELETE FROM proactive_candidates
                        WHERE user_id = :user_id AND status = 'pending' AND channel = :channel
                        """
                    ),
                    {"user_id": self.user_id, "channel": channel},
                )
                for candidate in candidates:
                    connection.execute(
                        text(
                            """
                            INSERT INTO proactive_candidates (
                                id, user_id, trigger, message, status, channel, scheduled_for,
                                delivered_at, metadata_json, created_at, updated_at
                            )
                            VALUES (
                                :id, :user_id, :trigger, :message, :status, :channel, :scheduled_for,
                                :delivered_at, :metadata_json, :created_at, :updated_at
                            )
                            """
                        ),
                        {
                            "id": str(uuid4()),
                            "user_id": self.user_id,
                            "trigger": str(candidate.get("trigger") or ""),
                            "message": str(candidate.get("message") or ""),
                            "status": str(candidate.get("status") or "pending"),
                            "channel": str(candidate.get("channel") or channel),
                            "scheduled_for": candidate.get("scheduled_for"),
                            "delivered_at": candidate.get("delivered_at"),
                            "metadata_json": json.dumps(candidate.get("metadata") or {}, ensure_ascii=True),
                            "created_at": now_iso,
                            "updated_at": now_iso,
                        },
                    )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def list_pending(self, *, channel: str | None = None, limit: int = 20) -> list[dict[str, object]]:
        return self.list(channel=channel, status="pending", limit=limit)

    def list(
        self,
        *,
        channel: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        predicates = ["user_id = :user_id", "status = 'pending'"]
        params: dict[str, object] = {"user_id": self.user_id, "limit": limit}
        if status is None:
            predicates = ["user_id = :user_id"]
        else:
            predicates = ["user_id = :user_id", "status = :status"]
            params["status"] = status
        if channel is not None:
            predicates.append("channel = :channel")
            params["channel"] = channel
        where_sql = " AND ".join(predicates)
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        f"""
                        SELECT id, trigger, message, status, channel, scheduled_for, delivered_at, metadata_json, created_at, updated_at
                        FROM proactive_candidates
                        WHERE {where_sql}
                        ORDER BY created_at DESC
                        LIMIT :limit
                        """
                    ),
                    params,
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [dict(row) for row in rows]

    def mark_delivered(self, candidate_id: str, *, status: str = "delivered") -> None:
        now_iso = utcnow_iso()
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE proactive_candidates
                        SET status = :status,
                            delivered_at = :delivered_at,
                            updated_at = :updated_at
                        WHERE id = :candidate_id
                        """
                    ),
                    {
                        "status": status,
                        "delivered_at": now_iso,
                        "updated_at": now_iso,
                        "candidate_id": candidate_id,
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def clear_pending(self, *, channel: str | None = None) -> None:
        predicates = ["user_id = :user_id", "status = 'pending'"]
        params: dict[str, object] = {"user_id": self.user_id}
        if channel is not None:
            predicates.append("channel = :channel")
            params["channel"] = channel
        where_sql = " AND ".join(predicates)
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(text(f"DELETE FROM proactive_candidates WHERE {where_sql}"), params)
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
