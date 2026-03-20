"""Tests for SQL injection guards in soul/db.py.

Covers _validate_sql_identifier, _ensure_columns, and migrate_postgres_jsonb.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from soul import db
from soul.db import (
    _ALLOWED_COLUMN_DEFINITIONS,
    _ALLOWED_TABLE_NAMES,
    _validate_sql_identifier,
)


# ---------------------------------------------------------------------------
# _validate_sql_identifier
# ---------------------------------------------------------------------------


class TestValidateSqlIdentifier:
    def test_accepts_simple_name(self):
        _validate_sql_identifier("column_name", "col")  # must not raise

    def test_accepts_leading_underscore(self):
        _validate_sql_identifier("_private", "col")

    def test_accepts_mixed_case_with_digits(self):
        _validate_sql_identifier("Col1_Name2", "col")

    def test_rejects_semicolon(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_sql_identifier("col; DROP TABLE users--", "col")

    def test_rejects_space(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_sql_identifier("col name", "col")

    def test_rejects_leading_digit(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_sql_identifier("1col", "col")

    def test_rejects_dash(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_sql_identifier("col-name", "col")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_sql_identifier("", "col")

    def test_rejects_sql_comment_injection(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_sql_identifier("col--comment", "col")

    def test_rejects_parenthesis(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_sql_identifier("col()", "col")


# ---------------------------------------------------------------------------
# _ensure_columns — table name allowlist
# ---------------------------------------------------------------------------


class TestEnsureColumnsTableAllowlist:
    def _make_db_with_table(self, tmp_path, table_name: str) -> str:
        database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        with db.connect(database_url) as conn:
            conn.execute(text(f'CREATE TABLE "{table_name}" (id TEXT PRIMARY KEY)'))
            conn.commit()
        return database_url

    def test_rejects_unknown_table(self, tmp_path):
        database_url = self._make_db_with_table(tmp_path, "unknown_table")
        engine = db._get_engine(database_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            with pytest.raises(ValueError, match="not in the allowed list"):
                db._ensure_columns(
                    conn,
                    inspector=inspector,
                    table_name="unknown_table",
                    columns={"new_col": "INTEGER DEFAULT 0"},
                )

    def test_rejects_injection_in_table_name(self, tmp_path):
        database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        engine = db._get_engine(database_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            with pytest.raises(ValueError):
                db._ensure_columns(
                    conn,
                    inspector=inspector,
                    table_name="episodic_memory; DROP TABLE users--",
                    columns={"new_col": "INTEGER DEFAULT 0"},
                )


# ---------------------------------------------------------------------------
# _ensure_columns — column name and definition validation
# ---------------------------------------------------------------------------


class TestEnsureColumnsColumnValidation:
    def _make_episodic_db(self, tmp_path) -> str:
        database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        with db.connect(database_url) as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE episodic_memory (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL
                    )
                    """
                )
            )
            conn.commit()
        return database_url

    def test_rejects_injection_in_column_name(self, tmp_path):
        database_url = self._make_episodic_db(tmp_path)
        engine = db._get_engine(database_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            with pytest.raises(ValueError, match="Unsafe SQL identifier"):
                db._ensure_columns(
                    conn,
                    inspector=inspector,
                    table_name="episodic_memory",
                    columns={"evil; DROP TABLE episodic_memory--": "INTEGER DEFAULT 0"},
                )

    def test_rejects_unknown_definition(self, tmp_path):
        database_url = self._make_episodic_db(tmp_path)
        engine = db._get_engine(database_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            with pytest.raises(ValueError, match="not in the allowed list"):
                db._ensure_columns(
                    conn,
                    inspector=inspector,
                    table_name="episodic_memory",
                    columns={"new_col": "TEXT; DROP TABLE episodic_memory--"},
                )

    def test_accepts_all_known_definitions(self, tmp_path):
        """Every definition in _ALLOWED_COLUMN_DEFINITIONS must be accepted."""
        database_url = self._make_episodic_db(tmp_path)
        engine = db._get_engine(database_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            for i, definition in enumerate(_ALLOWED_COLUMN_DEFINITIONS):
                col_name = f"safe_col_{i}"
                # Should not raise
                db._ensure_columns(
                    conn,
                    inspector=inspector,
                    table_name="episodic_memory",
                    columns={col_name: definition},
                )

    def test_skips_existing_columns_without_error(self, tmp_path):
        """Columns already present are silently skipped — no DDL executed."""
        database_url = self._make_episodic_db(tmp_path)
        engine = db._get_engine(database_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            # "id" already exists; passing an invalid definition for it must not
            # raise because the column is skipped before validation.
            db._ensure_columns(
                conn,
                inspector=inspector,
                table_name="episodic_memory",
                columns={"id": "INJECTED DEFINITION"},
            )


# ---------------------------------------------------------------------------
# migrate_postgres_jsonb — skips non-postgres URLs
# ---------------------------------------------------------------------------


class TestMigratePostgresJsonb:
    def test_skips_sqlite(self, tmp_path):
        database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
        result = db.migrate_postgres_jsonb(database_url)
        assert result == {"skipped": True, "reason": "not postgresql"}

    def test_skips_plain_path(self, tmp_path):
        result = db.migrate_postgres_jsonb(tmp_path / "soul.db")
        assert result == {"skipped": True, "reason": "not postgresql"}


# ---------------------------------------------------------------------------
# Allowlist completeness — guard against accidental shrinkage
# ---------------------------------------------------------------------------


def test_allowed_table_names_non_empty():
    assert len(_ALLOWED_TABLE_NAMES) >= 3


def test_allowed_column_definitions_non_empty():
    assert len(_ALLOWED_COLUMN_DEFINITIONS) >= 11
