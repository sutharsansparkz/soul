from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SharedLanguageEntry:
    phrase: str
    meaning: str = ""
    count: int = 1
