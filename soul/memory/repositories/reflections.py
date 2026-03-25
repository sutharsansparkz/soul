"""Repository for reflection artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import connect, get_engine, utcnow_iso


@dataclass(slots=True)
class ReflectionArtifact:
    date: str
    summary: str
    insights: list[str]


class ReflectionArtifactsRepository:
    def __init__(self, database: str | Path, *, user_id: str = "local-user"):
        self.database = database
        self.user_id = user_id

    def load(self) -> list[ReflectionArtifact]:
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT reflection_key, summary, insights_json
                        FROM reflection_artifacts
                        WHERE user_id = :user_id
                        ORDER BY created_at ASC
                        """
                    ),
                    {"user_id": self.user_id},
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [
            ReflectionArtifact(
                date=str(row["reflection_key"]),
                summary=str(row["summary"]),
                insights=[str(item) for item in json.loads(str(row["insights_json"]))],
            )
            for row in rows
        ]

    def get_by_key(self, reflection_key: str) -> ReflectionArtifact | None:
        try:
            with connect(self.database) as connection:
                row = connection.execute(
                    text(
                        """
                        SELECT reflection_key, summary, insights_json
                        FROM reflection_artifacts
                        WHERE user_id = :user_id AND reflection_key = :reflection_key
                        LIMIT 1
                        """
                    ),
                    {"user_id": self.user_id, "reflection_key": reflection_key},
                ).mappings().first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        if row is None:
            return None
        return ReflectionArtifact(
            date=str(row["reflection_key"]),
            summary=str(row["summary"]),
            insights=[str(item) for item in json.loads(str(row["insights_json"]))],
        )

    def append(self, entry: ReflectionArtifact, *, trace_id: str | None = None, source: str = "reflection") -> None:
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO reflection_artifacts (
                            id, user_id, reflection_key, summary, insights_json, source, trace_id, created_at
                        )
                        VALUES (
                            :id, :user_id, :reflection_key, :summary, :insights_json, :source, :trace_id, :created_at
                        )
                        ON CONFLICT(user_id, reflection_key) DO UPDATE SET
                            summary = excluded.summary,
                            insights_json = excluded.insights_json,
                            source = excluded.source,
                            trace_id = excluded.trace_id,
                            created_at = excluded.created_at
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "user_id": self.user_id,
                        "reflection_key": entry.date,
                        "summary": entry.summary,
                        "insights_json": json.dumps(entry.insights, ensure_ascii=True),
                        "source": source,
                        "trace_id": trace_id,
                        "created_at": utcnow_iso(),
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
