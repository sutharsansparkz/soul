"""Key-value application settings stored in SQLite."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import get_engine, utcnow_iso


class AppSettingsRepository:
    def __init__(self, database: str | Path):
        self.database = database

    def get(self, key: str, default: object | None = None) -> object | None:
        try:
            with get_engine(self.database).begin() as connection:
                row = connection.execute(
                    text("SELECT value_json FROM app_settings WHERE key = :key"),
                    {"key": key},
                ).first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        if row is None:
            return default
        try:
            return json.loads(str(row[0]))
        except json.JSONDecodeError:
            return str(row[0])

    def set(self, key: str, value: object) -> None:
        try:
            payload = json.dumps(value, ensure_ascii=True)
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO app_settings (key, value_json, updated_at)
                        VALUES (:key, :value_json, :updated_at)
                        ON CONFLICT(key) DO UPDATE SET
                            value_json = excluded.value_json,
                            updated_at = excluded.updated_at
                        """
                    ),
                    {
                        "key": key,
                        "value_json": payload,
                        "updated_at": utcnow_iso(),
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
