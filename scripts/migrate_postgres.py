"""Standalone PostgreSQL JSONB migration runner.
Usage: python -m scripts.migrate_postgres
Reads DATABASE_URL from environment / .env file.
"""

from __future__ import annotations

from soul import db
from soul.config import get_settings


def main() -> None:
    settings = get_settings()
    result = db.migrate_postgres_jsonb(settings.database_url)
    print(result)


if __name__ == "__main__":
    main()
