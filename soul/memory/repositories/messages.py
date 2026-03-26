"""Repositories for sessions and message history."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.persistence.db import connect, get_engine, utcnow_iso


class MessagesRepository:
    def __init__(self, database: str | Path, *, user_id: str = "local-user"):
        self.database = database
        self.user_id = user_id

    def ensure_user(self) -> None:
        now_iso = utcnow_iso()
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO users (id, created_at, updated_at)
                        VALUES (:id, :created_at, :updated_at)
                        ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
                        """
                    ),
                    {"id": self.user_id, "created_at": now_iso, "updated_at": now_iso},
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def create_session(self, companion_name: str, *, session_id: str | None = None) -> str:
        session_id = session_id or str(uuid4())
        self.ensure_user()
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO sessions (id, companion_name, user_id, started_at, metadata_json)
                        VALUES (:id, :companion_name, :user_id, :started_at, :metadata_json)
                        """
                    ),
                    {
                        "id": session_id,
                        "companion_name": companion_name,
                        "user_id": self.user_id,
                        "started_at": utcnow_iso(),
                        "metadata_json": "{}",
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return session_id

    def session_exists(self, session_id: str) -> bool:
        try:
            with connect(self.database) as connection:
                row = connection.execute(
                    text("SELECT 1 FROM sessions WHERE id = :session_id LIMIT 1"),
                    {"session_id": session_id},
                ).first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return row is not None

    def close_session(self, session_id: str) -> None:
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text("UPDATE sessions SET ended_at = :ended_at WHERE id = :session_id"),
                    {"ended_at": utcnow_iso(), "session_id": session_id},
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def close_open_sessions_with_prefix(self, session_prefix: str, *, except_session_id: str | None = None) -> int:
        try:
            with get_engine(self.database).begin() as connection:
                result = connection.execute(
                    text(
                        """
                        UPDATE sessions
                        SET ended_at = :ended_at
                        WHERE id LIKE :pattern
                          AND ended_at IS NULL
                          AND (:except_session_id IS NULL OR id != :except_session_id)
                        """
                    ),
                    {
                        "ended_at": utcnow_iso(),
                        "pattern": f"{session_prefix}%",
                        "except_session_id": except_session_id,
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return int(result.rowcount or 0)

    def log_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        user_mood: str | None = None,
        companion_state: str | None = None,
        provider: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str:
        message_id = str(uuid4())
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO messages (
                            id, session_id, role, content, user_mood, companion_state, provider, created_at, metadata_json
                        )
                        VALUES (
                            :id, :session_id, :role, :content, :user_mood, :companion_state, :provider, :created_at, :metadata_json
                        )
                        """
                    ),
                    {
                        "id": message_id,
                        "session_id": session_id,
                        "role": role,
                        "content": content,
                        "user_mood": user_mood,
                        "companion_state": companion_state,
                        "provider": provider,
                        "created_at": utcnow_iso(),
                        "metadata_json": json.dumps(metadata or {}, ensure_ascii=True),
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return message_id

    def get_session_messages(self, session_id: str) -> list[dict[str, object]]:
        return self._fetch_dicts(
            """
            SELECT id, role, content, user_mood, companion_state, provider, created_at, metadata_json
            FROM messages
            WHERE session_id = :session_id
            ORDER BY created_at ASC
            """,
            {"session_id": session_id},
        )

    def get_recent_session_messages(self, session_id: str, *, limit: int = 12) -> list[dict[str, object]]:
        rows = self._fetch_dicts(
            """
            SELECT id, role, content, user_mood, companion_state, provider, created_at, metadata_json
            FROM messages
            WHERE session_id = :session_id
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"session_id": session_id, "limit": limit},
        )
        return list(reversed(rows))

    def get_last_completed_session_id(self, *, current_session_id: str | None = None) -> str | None:
        try:
            with connect(self.database) as connection:
                row = connection.execute(
                    text(
                        """
                        SELECT id
                        FROM sessions
                        WHERE ended_at IS NOT NULL
                          AND (:current_session_id IS NULL OR id != :current_session_id)
                        ORDER BY started_at DESC
                        LIMIT 1
                        """
                    ),
                    {"current_session_id": current_session_id},
                ).first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return str(row[0]) if row else None

    def list_sessions(self, *, limit: int | None = None, completed_only: bool = False) -> list[dict[str, object]]:
        predicates = []
        params: dict[str, object] = {}
        if completed_only:
            predicates.append("ended_at IS NOT NULL")
        where_sql = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        limit_sql = ""
        if limit is not None:
            params["limit"] = limit
            limit_sql = "LIMIT :limit"
        return self._fetch_dicts(
            f"""
            SELECT id, companion_name, user_id, started_at, ended_at, metadata_json
            FROM sessions
            {where_sql}
            ORDER BY started_at DESC
            {limit_sql}
            """,
            params,
        )

    def count_sessions(self) -> int:
        return self._count(
            "SELECT COUNT(*) FROM sessions WHERE user_id = :user_id",
            {"user_id": self.user_id},
        )

    def count_messages(self, *, role: str | None = None) -> int:
        if role is None:
            return self._count(
                "SELECT COUNT(*) FROM messages WHERE session_id IN "
                "(SELECT id FROM sessions WHERE user_id = :user_id)",
                {"user_id": self.user_id},
            )
        return self._count(
            "SELECT COUNT(*) FROM messages WHERE role = :role AND session_id IN "
            "(SELECT id FROM sessions WHERE user_id = :user_id)",
            {"role": role, "user_id": self.user_id},
        )

    def get_last_message_timestamp(self) -> str | None:
        try:
            with connect(self.database) as connection:
                row = connection.execute(
                    text("SELECT created_at FROM messages ORDER BY created_at DESC LIMIT 1")
                ).first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return str(row[0]) if row else None

    def list_user_message_moods_since(self, moods: tuple[str, ...], *, since: str) -> list[dict[str, object]]:
        placeholders = ", ".join(f":mood_{index}" for index in range(len(moods)))
        params: dict[str, object] = {"since": since}
        params.update({f"mood_{index}": mood for index, mood in enumerate(moods)})
        return self._fetch_dicts(
            f"""
            SELECT id, session_id, content, user_mood, created_at
            FROM messages
            WHERE role = 'user'
              AND created_at >= :since
              AND user_mood IN ({placeholders})
            ORDER BY created_at DESC
            """,
            params,
        )

    def list_unconsolidated_completed_session_ids(self) -> list[str]:
        rows = self._fetch_dicts(
            """
            SELECT s.id
            FROM sessions s
            LEFT JOIN consolidated_sessions c ON c.session_id = s.id
            WHERE s.ended_at IS NOT NULL
              AND c.session_id IS NULL
            ORDER BY s.started_at ASC
            """
        )
        return [str(row["id"]) for row in rows]

    def mark_session_consolidated(
        self,
        session_id: str,
        *,
        source: str = "maintenance",
        connection=None,  # type: ignore[no-untyped-def]
    ) -> None:
        try:
            if connection is None:
                with get_engine(self.database).begin() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO consolidated_sessions (session_id, consolidated_at, source)
                            VALUES (:session_id, :consolidated_at, :source)
                            ON CONFLICT(session_id) DO UPDATE SET
                                consolidated_at = excluded.consolidated_at,
                                source = excluded.source
                            """
                        ),
                        {"session_id": session_id, "consolidated_at": utcnow_iso(), "source": source},
                    )
                return
            connection.execute(
                text(
                    """
                    INSERT INTO consolidated_sessions (session_id, consolidated_at, source)
                    VALUES (:session_id, :consolidated_at, :source)
                    ON CONFLICT(session_id) DO UPDATE SET
                        consolidated_at = excluded.consolidated_at,
                        source = excluded.source
                    """
                ),
                {"session_id": session_id, "consolidated_at": utcnow_iso(), "source": source},
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def get_session_memory_export_state(self, session_id: str) -> dict[str, object] | None:
        rows = self._fetch_dicts(
            """
            SELECT session_id, exported_at, exported_user_count
            FROM session_memory_exports
            WHERE session_id = :session_id
            LIMIT 1
            """,
            {"session_id": session_id},
        )
        return rows[0] if rows else None

    def mark_session_memory_exported(self, session_id: str, *, exported_user_count: int) -> None:
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO session_memory_exports (session_id, exported_at, exported_user_count)
                        VALUES (:session_id, :exported_at, :exported_user_count)
                        ON CONFLICT(session_id) DO UPDATE SET
                            exported_at = excluded.exported_at,
                            exported_user_count = excluded.exported_user_count
                        """
                    ),
                    {
                        "session_id": session_id,
                        "exported_at": utcnow_iso(),
                        "exported_user_count": exported_user_count,
                    },
                )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def _count(self, statement: str, params: dict[str, object] | None = None) -> int:
        try:
            with connect(self.database) as connection:
                row = connection.execute(text(statement), params or {}).first()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return int(row[0] if row else 0)

    def _fetch_dicts(self, statement: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        try:
            with connect(self.database) as connection:
                rows = connection.execute(text(statement), params or {}).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [dict(row) for row in rows]
