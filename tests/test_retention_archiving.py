from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from soul import db
from soul.tasks.consolidate import archive_and_purge_old_session_messages
from sqlalchemy import text


def test_archive_and_purge_old_session_messages_archives_then_deletes_raw_messages(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    old_session = db.create_session(database_url, "Ara")
    db.log_message(database_url, session_id=old_session, role="user", content="old user message")
    db.log_message(database_url, session_id=old_session, role="assistant", content="old assistant message")
    db.close_session(database_url, old_session)

    recent_session = db.create_session(database_url, "Ara")
    db.log_message(database_url, session_id=recent_session, role="user", content="recent user message")
    db.close_session(database_url, recent_session)

    old_date = datetime.now(timezone.utc) - timedelta(days=120)
    with db.connect(database_url) as connection:
        connection.execute(
            text("UPDATE sessions SET ended_at = :ended_at WHERE id = :session_id"),
            {"ended_at": old_date.replace(microsecond=0).isoformat(), "session_id": old_session},
        )
        connection.commit()

    archive_dir = tmp_path / "archive"
    result = archive_and_purge_old_session_messages(
        database_url=database_url,
        archive_dir=archive_dir,
        retention_days=90,
        now=datetime.now(timezone.utc),
    )

    assert result["archived_sessions"] == 1
    assert result["purged_messages"] >= 2
    assert (archive_dir / f"{old_session}.jsonl").exists()
    assert db.get_session_messages(database_url, old_session) == []
    assert db.get_session_messages(database_url, recent_session)


def test_archive_and_purge_does_not_delete_messages_when_archive_write_fails(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    old_session = db.create_session(database_url, "Ara")
    db.log_message(database_url, session_id=old_session, role="user", content="keep me")
    db.close_session(database_url, old_session)

    old_date = datetime.now(timezone.utc) - timedelta(days=120)
    with db.connect(database_url) as connection:
        connection.execute(
            text("UPDATE sessions SET ended_at = :ended_at WHERE id = :session_id"),
            {"ended_at": old_date.replace(microsecond=0).isoformat(), "session_id": old_session},
        )
        connection.commit()

    original_write_text = Path.write_text

    def failing_write_text(self, data, *args, **kwargs):  # noqa: ANN001
        if self.name == f"{old_session}.jsonl":
            raise OSError("disk full")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)
    result = archive_and_purge_old_session_messages(
        database_url=database_url,
        archive_dir=tmp_path / "archive",
        retention_days=90,
        now=datetime.now(timezone.utc),
    )

    assert result["failed_sessions"] == 1
    assert db.get_session_messages(database_url, old_session)
