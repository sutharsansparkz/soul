"""Repository for auditable milestone records."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import connect, get_engine, utcnow_iso


class MilestonesRepository:
    def __init__(self, database: str | Path):
        self.database = database

    def exists(self, kind: str) -> bool:
        try:
            with connect(self.database) as connection:
                row = connection.execute(
                    text("SELECT 1 FROM milestones WHERE kind = :kind LIMIT 1"),
                    {"kind": kind},
                ).first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return row is not None

    def record(
        self,
        *,
        kind: str,
        note: str,
        session_id: str | None = None,
        title: str = "",
        description: str = "",
        category: str = "relationship",
        metadata: dict[str, object] | None = None,
        occurred_at: str | None = None,
    ) -> str:
        milestone_id = str(uuid4())
        now_iso = utcnow_iso()
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO milestones (
                            id, kind, note, session_id, occurred_at, title, description, category, metadata_json, created_at
                        )
                        VALUES (
                            :id, :kind, :note, :session_id, :occurred_at, :title, :description, :category, :metadata_json, :created_at
                        )
                        """
                    ),
                    {
                        "id": milestone_id,
                        "kind": kind,
                        "note": note,
                        "session_id": session_id,
                        "occurred_at": occurred_at or now_iso,
                        "title": title or kind,
                        "description": description or note,
                        "category": category,
                        "metadata_json": json.dumps(metadata or {}, ensure_ascii=True),
                        "created_at": now_iso,
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return milestone_id

    def list(self, *, limit: int = 200) -> list[dict[str, object]]:
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT id, kind, note, session_id, occurred_at, title, description, category, metadata_json, created_at
                        FROM milestones
                        ORDER BY occurred_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [dict(row) for row in rows]
