"""SQLite-backed mood snapshot repository."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import connect, get_engine, utcnow_iso


class MoodSnapshotsRepository:
    def __init__(self, database: str | Path, *, user_id: str = "local-user"):
        self.database = database
        self.user_id = user_id

    def add_snapshot(
        self,
        *,
        session_id: str | None,
        message_id: str | None,
        user_mood: str,
        companion_state: str,
        confidence: float,
        rationale: str,
        created_at: str | None = None,
    ) -> str:
        snapshot_id = str(uuid4())
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO mood_snapshots (
                            id, user_id, session_id, message_id, user_mood, companion_state,
                            confidence, rationale, created_at
                        )
                        VALUES (
                            :id, :user_id, :session_id, :message_id, :user_mood, :companion_state,
                            :confidence, :rationale, :created_at
                        )
                        """
                    ),
                    {
                        "id": snapshot_id,
                        "user_id": self.user_id,
                        "session_id": session_id,
                        "message_id": message_id,
                        "user_mood": user_mood,
                        "companion_state": companion_state,
                        "confidence": confidence,
                        "rationale": rationale,
                        "created_at": created_at or utcnow_iso(),
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return snapshot_id

    def current_state(self) -> dict[str, object] | None:
        try:
            with connect(self.database) as connection:
                row = connection.execute(
                    text(
                        """
                        SELECT id, session_id, message_id, user_mood, companion_state, confidence, rationale, created_at
                        FROM mood_snapshots
                        WHERE user_id = :user_id
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"user_id": self.user_id},
                ).mappings().first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        if row is None:
            return None
        payload = dict(row)
        payload["state"] = payload.get("companion_state")
        payload["updated_at"] = payload.get("created_at")
        payload["last_user_mood"] = payload.get("user_mood")
        return payload

    def latest(self) -> dict[str, object] | None:
        return self.current_state()
