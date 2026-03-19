from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from datetime import datetime, timezone
import json
from uuid import uuid4


@dataclass(slots=True)
class SessionMessage:
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class Session:
    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "unknown"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str | None = None
    messages: list[SessionMessage] = field(default_factory=list)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(SessionMessage(role=role, content=content))

    def finish(self) -> None:
        self.ended_at = datetime.now(timezone.utc).isoformat()


class SessionRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, session: Session) -> None:
        payload = asdict(session)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def load(self) -> Session | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        session = Session(
            id=payload["id"],
            user_id=payload.get("user_id", "unknown"),
            started_at=payload.get("started_at", ""),
            ended_at=payload.get("ended_at"),
        )
        session.messages = [SessionMessage(**message) for message in payload.get("messages", [])]
        return session
