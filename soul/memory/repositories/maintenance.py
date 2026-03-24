"""Repository for maintenance run bookkeeping."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import connect, get_engine, utcnow_iso


class MaintenanceRunRepository:
    def __init__(self, database: str | Path):
        self.database = database

    def start(self, job_name: str, *, details: dict[str, object] | None = None) -> str:
        run_id = str(uuid4())
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO maintenance_runs (id, job_name, status, started_at, details_json)
                        VALUES (:id, :job_name, :status, :started_at, :details_json)
                        """
                    ),
                    {
                        "id": run_id,
                        "job_name": job_name,
                        "status": "running",
                        "started_at": utcnow_iso(),
                        "details_json": json.dumps(details or {}, ensure_ascii=True),
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return run_id

    def finish(
        self,
        run_id: str,
        *,
        status: str,
        details: dict[str, object] | None = None,
        error: str | None = None,
    ) -> None:
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE maintenance_runs
                        SET status = :status,
                            completed_at = :completed_at,
                            details_json = :details_json,
                            error = :error
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": run_id,
                        "status": status,
                        "completed_at": utcnow_iso(),
                        "details_json": json.dumps(details or {}, ensure_ascii=True),
                        "error": error,
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def list_recent(self, *, limit: int = 20) -> list[dict[str, object]]:
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT id, job_name, status, started_at, completed_at, details_json, error
                        FROM maintenance_runs
                        ORDER BY started_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [dict(row) for row in rows]
