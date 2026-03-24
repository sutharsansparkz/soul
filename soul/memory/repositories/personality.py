"""Repository for versioned personality state."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import connect, get_engine, utcnow_iso


class PersonalityStateRepository:
    def __init__(self, database: str | Path, *, user_id: str = "local-user"):
        self.database = database
        self.user_id = user_id

    def get_current_state(self) -> dict[str, float]:
        try:
            with connect(self.database) as connection:
                row = connection.execute(
                    text(
                        """
                        SELECT state_json
                        FROM personality_state
                        WHERE user_id = :user_id
                        ORDER BY version DESC, created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"user_id": self.user_id},
                ).first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        if row is None:
            return {}
        return json.loads(str(row[0]))

    def list_history(self, *, limit: int = 20) -> list[dict[str, object]]:
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT id, version, state_json, resonance_signals_json, notes, source, created_at
                        FROM personality_state
                        WHERE user_id = :user_id
                        ORDER BY version DESC, created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"user_id": self.user_id, "limit": limit},
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [dict(row) for row in rows]

    def record_state(
        self,
        state: dict[str, float],
        *,
        resonance_signals: dict[str, float] | None = None,
        notes: str = "",
        source: str = "runtime",
    ) -> dict[str, object]:
        now_iso = utcnow_iso()
        next_version = 1
        try:
            with get_engine(self.database).begin() as connection:
                row = connection.execute(
                    text("SELECT MAX(version) FROM personality_state WHERE user_id = :user_id"),
                    {"user_id": self.user_id},
                ).first()
                max_version = int(row[0]) if row and row[0] is not None else 0
                next_version = max_version + 1
                connection.execute(
                    text(
                        """
                        INSERT INTO personality_state (
                            id, user_id, version, state_json, resonance_signals_json, notes, source, created_at
                        )
                        VALUES (
                            :id, :user_id, :version, :state_json, :resonance_signals_json, :notes, :source, :created_at
                        )
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "user_id": self.user_id,
                        "version": next_version,
                        "state_json": json.dumps(state, ensure_ascii=True),
                        "resonance_signals_json": json.dumps(resonance_signals or {}, ensure_ascii=True),
                        "notes": notes,
                        "source": source,
                        "created_at": now_iso,
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return {"version": next_version, "state": state, "created_at": now_iso}
