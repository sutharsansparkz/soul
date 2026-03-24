"""Turn tracing persisted in SQLite."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import connect, get_engine, utcnow_iso


class TurnTraceRepository:
    def __init__(self, database: str | Path):
        self.database = database

    def write_trace(
        self,
        *,
        session_id: str,
        input_message_id: str | None,
        reply_message_id: str | None,
        payload: dict[str, object],
        status: str = "ok",
        error: str | None = None,
    ) -> str:
        trace_id = str(uuid4())
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO turn_traces (
                            id, session_id, input_message_id, reply_message_id, status, trace_json, error, created_at
                        )
                        VALUES (
                            :id, :session_id, :input_message_id, :reply_message_id, :status, :trace_json, :error, :created_at
                        )
                        """
                    ),
                    {
                        "id": trace_id,
                        "session_id": session_id,
                        "input_message_id": input_message_id,
                        "reply_message_id": reply_message_id,
                        "status": status,
                        "trace_json": json.dumps(payload, ensure_ascii=True),
                        "error": error,
                        "created_at": utcnow_iso(),
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return trace_id

    def get_last_trace(self) -> dict[str, object] | None:
        return self._get_one(
            """
            SELECT id, session_id, input_message_id, reply_message_id, status, trace_json, error, created_at
            FROM turn_traces
            ORDER BY created_at DESC
            LIMIT 1
            """
        )

    def get_trace(self, trace_id: str) -> dict[str, object] | None:
        return self._get_one(
            """
            SELECT id, session_id, input_message_id, reply_message_id, status, trace_json, error, created_at
            FROM turn_traces
            WHERE id = :trace_id
            LIMIT 1
            """,
            {"trace_id": trace_id},
        )

    def list_recent(self, *, limit: int = 20) -> list[dict[str, object]]:
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT id, session_id, input_message_id, reply_message_id, status, trace_json, error, created_at
                        FROM turn_traces
                        ORDER BY created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [self._inflate(dict(row)) for row in rows]

    def _get_one(self, statement: str, params: dict[str, object] | None = None) -> dict[str, object] | None:
        try:
            with connect(self.database) as connection:
                row = connection.execute(text(statement), params or {}).mappings().first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        if row is None:
            return None
        return self._inflate(dict(row))

    def _inflate(self, row: dict[str, object]) -> dict[str, object]:
        try:
            row["trace"] = json.loads(str(row.pop("trace_json", "{}")))
        except json.JSONDecodeError:
            row["trace"] = {"raw": row.get("trace_json", "{}")}
        return row
