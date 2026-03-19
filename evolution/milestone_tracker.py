from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass(slots=True)
class Milestone:
    date: str
    title: str
    description: str
    category: str = "relationship"


class MilestoneTracker:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[Milestone]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [Milestone(**item) for item in payload]

    def record(self, milestone: Milestone) -> Milestone:
        items = self.load()
        items.append(milestone)
        self.path.write_text(json.dumps([asdict(item) for item in items], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        return milestone
