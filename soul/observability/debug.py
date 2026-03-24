"""Debug payload helpers backed by SQLite traces."""

from __future__ import annotations

import json


def pretty_json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)
