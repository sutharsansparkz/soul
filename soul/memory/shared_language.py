from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json


@dataclass(slots=True)
class SharedLanguageEntry:
    phrase: str
    meaning: str = ""
    count: int = 1


class SharedLanguageStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[SharedLanguageEntry]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [SharedLanguageEntry(**item) for item in payload]

    def save(self, entries: list[SharedLanguageEntry]) -> None:
        payload = [asdict(entry) for entry in entries]
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def register(self, phrase: str, meaning: str = "") -> SharedLanguageEntry:
        entries = self.load()
        for entry in entries:
            if entry.phrase == phrase:
                entry.count += 1
                if meaning and not entry.meaning:
                    entry.meaning = meaning
                self.save(entries)
                return entry
        entry = SharedLanguageEntry(phrase=phrase, meaning=meaning, count=1)
        entries.append(entry)
        self.save(entries)
        return entry
