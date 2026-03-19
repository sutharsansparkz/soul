from __future__ import annotations

from pathlib import Path

from soul import db


def ensure_fts_index(database: Path | str) -> None:
    """Ensure SQLite FTS5 index + triggers exist and are initialized."""
    db.ensure_memory_fts(database)


def rebuild_fts_index(database: Path | str) -> None:
    db.rebuild_memory_fts(database)


def search_fts(
    database: Path | str,
    query: str,
    *,
    user_id: str | None = None,
    include_cold: bool = True,
    limit: int = 20,
) -> list[dict[str, object]]:
    return db.search_episodic_memories_fts(
        database,
        query,
        user_id=user_id,
        include_cold=include_cold,
        limit=limit,
    )
