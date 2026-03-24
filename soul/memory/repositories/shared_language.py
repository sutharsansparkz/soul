"""Repository for shared language entries."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.memory.shared_language import SharedLanguageEntry
from soul.persistence.db import connect, get_engine, utcnow_iso


class SharedLanguageRepository:
    def __init__(self, database: str | Path, *, user_id: str = "local-user"):
        self.database = database
        self.user_id = user_id

    def load(self) -> list[SharedLanguageEntry]:
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT phrase, meaning, count
                        FROM shared_language_entries
                        WHERE user_id = :user_id
                        ORDER BY count DESC, last_seen_at DESC
                        """
                    ),
                    {"user_id": self.user_id},
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [SharedLanguageEntry(**dict(row)) for row in rows]

    def register(self, phrase: str, meaning: str = "") -> SharedLanguageEntry:
        now_iso = utcnow_iso()
        try:
            with get_engine(self.database).begin() as connection:
                existing = connection.execute(
                    text(
                        """
                        SELECT id, phrase, meaning, count
                        FROM shared_language_entries
                        WHERE user_id = :user_id AND phrase = :phrase
                        LIMIT 1
                        """
                    ),
                    {"user_id": self.user_id, "phrase": phrase},
                ).mappings().first()
                if existing is not None:
                    count = int(existing["count"]) + 1
                    resolved_meaning = meaning or str(existing["meaning"])
                    connection.execute(
                        text(
                            """
                            UPDATE shared_language_entries
                            SET meaning = :meaning,
                                count = :count,
                                last_seen_at = :last_seen_at,
                                updated_at = :updated_at
                            WHERE id = :id
                            """
                        ),
                        {
                            "id": str(existing["id"]),
                            "meaning": resolved_meaning,
                            "count": count,
                            "last_seen_at": now_iso,
                            "updated_at": now_iso,
                        },
                    )
                    return SharedLanguageEntry(phrase=phrase, meaning=resolved_meaning, count=count)

                connection.execute(
                    text(
                        """
                        INSERT INTO shared_language_entries (
                            id, user_id, phrase, meaning, count, first_seen_at, last_seen_at, created_at, updated_at
                        )
                        VALUES (
                            :id, :user_id, :phrase, :meaning, :count, :first_seen_at, :last_seen_at, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "user_id": self.user_id,
                        "phrase": phrase,
                        "meaning": meaning,
                        "count": 1,
                        "first_seen_at": now_iso,
                        "last_seen_at": now_iso,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return SharedLanguageEntry(phrase=phrase, meaning=meaning, count=1)
