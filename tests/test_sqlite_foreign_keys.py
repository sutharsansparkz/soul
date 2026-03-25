from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from soul import db
from soul.persistence.db import connect as persistence_connect


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

