from __future__ import annotations

from soul.db import migrate_postgres_jsonb


def test_postgres_migration_skips_for_sqlite(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"

    result = migrate_postgres_jsonb(database_url)

    assert result == {"skipped": True, "reason": "not postgresql"}
