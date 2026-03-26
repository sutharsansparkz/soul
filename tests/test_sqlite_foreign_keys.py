from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from soul import db
import soul.db as soul_db
from soul.persistence.db import connect as persistence_connect, get_engine as persistence_get_engine


def test_sqlite_foreign_keys_enforced_for_messages(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    # messages.session_id must reference sessions.id.
    with pytest.raises(IntegrityError):
        with persistence_connect(database_url) as connection:
            with connection.begin():
                connection.execute(
                    text(
                        """
                        INSERT INTO messages (
                            id, session_id, role, content, provider, created_at, metadata_json
                        )
                        VALUES (
                            :id, :session_id, :role, :content, :provider, :created_at, :metadata_json
                        )
                        """
                    ),
                    {
                        "id": "msg-1",
                        "session_id": "does-not-exist",
                        "role": "user",
                        "content": "orphan message",
                        "provider": "test",
                        "created_at": db.utcnow_iso(),
                        "metadata_json": "{}",
                    },
                )


def test_legacy_db_helpers_share_persistence_engine_configuration(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    assert soul_db._get_engine(database_url) is persistence_get_engine(database_url)

    with db.connect(database_url) as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()

    assert str(journal_mode).casefold() == "wal"
    assert int(busy_timeout) == 5000
    assert int(foreign_keys) == 1
