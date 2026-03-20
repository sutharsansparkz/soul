from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re


@dataclass(slots=True)
class BigMoment:
    date: str
    event: str
    emotional_weight: str = "medium"
    companion_was_there: bool = True


@dataclass(slots=True)
class UserStory:
    user_id: str = "unknown"
    updated_at: str = ""
    basics: dict[str, str] = field(default_factory=dict)
    current_chapter: dict[str, object] = field(default_factory=dict)
    big_moments: list[BigMoment] = field(default_factory=list)
    upcoming_events: list[dict[str, str]] = field(default_factory=list)
    relationships: list[dict[str, str]] = field(default_factory=list)
    values_observed: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    things_they_love: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StoryUpdateResult:
    changed: bool
    big_moment: BigMoment | None = None


BIG_MOMENT_PATTERNS = (
    "quit my job",
    "got engaged",
    "got married",
    "launched",
    "moved to",
    "broke up",
    "raised",
    "fundraising",
    "fired",
    "diagnosed",
    "graduated",
)

VALUE_KEYWORDS = {
    "honesty": "honesty",
    "creative": "creativity",
    "creativity": "creativity",
    "loyal": "loyalty",
    "loyalty": "loyalty",
    "independent": "independence",
    "independence": "independence",
    "curious": "curiosity",
}


class UserStoryRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> UserStory:
        if not self.path.exists():
            return UserStory()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        moments = [BigMoment(**item) for item in payload.get("big_moments", [])]
        payload["big_moments"] = moments
        return UserStory(**payload)

    def save(self, story: UserStory) -> None:
        payload = asdict(story)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass


def ensure_story_defaults(story: UserStory) -> UserStory:
    story.user_id = story.user_id or "unknown"
    story.basics = story.basics or {}
    story.current_chapter = story.current_chapter or {
        "summary": "",
        "active_goals": [],
        "active_fears": [],
        "current_mood_trend": "forming",
    }
    story.current_chapter.setdefault("summary", "")
    story.current_chapter.setdefault("active_goals", [])
    story.current_chapter.setdefault("active_fears", [])
    story.current_chapter.setdefault("current_mood_trend", "forming")
    story.big_moments = story.big_moments or []
    story.upcoming_events = story.upcoming_events or []
    story.relationships = story.relationships or []
    story.values_observed = story.values_observed or []
    story.triggers = story.triggers or []
    story.things_they_love = story.things_they_love or []
    return story


def apply_story_observations(
    story: UserStory,
    texts: list[str],
    *,
    mood_hint: str | None = None,
    observed_at: str | None = None,
) -> StoryUpdateResult:
    story = ensure_story_defaults(story)
    changed = False
    big_moment_added: BigMoment | None = None
    known_events = {moment.event for moment in story.big_moments}
    known_event_keys = {_event_key(moment.event) for moment in story.big_moments if moment.event.strip()}
    known_relationships = {
        (str(item.get("name", "")).casefold(), str(item.get("role", "")).casefold()) for item in story.relationships
    }

    for text in texts:
        stripped = text.strip()
        if not stripped:
            continue
        lowered = stripped.casefold()

        name = _capture_after(stripped, lowered, "my name is ")
        if name and story.basics.get("name") != name:
            story.basics["name"] = name
            changed = True

        location = _capture_after(stripped, lowered, "i live in ")
        if location and story.basics.get("location") != location:
            story.basics["location"] = location
            changed = True

        occupation = _capture_after(stripped, lowered, "i work as ")
        if occupation and story.basics.get("occupation") != occupation:
            story.basics["occupation"] = occupation
            changed = True

        birthday = _extract_birthday(stripped, lowered)
        if birthday and story.basics.get("birthday") != birthday:
            story.basics["birthday"] = birthday
            changed = True

        loved = _capture_after(stripped, lowered, "i love ")
        if loved and loved not in story.things_they_love:
            story.things_they_love.append(loved)
            changed = True

        upcoming_event = _extract_upcoming_event(stripped)
        if upcoming_event and upcoming_event not in story.upcoming_events:
            story.upcoming_events.append(upcoming_event)
            changed = True

        relationship = _extract_relationship(stripped)
        if relationship:
            key = (relationship["name"].casefold(), relationship["role"].casefold())
            if key not in known_relationships:
                story.relationships.append(relationship)
                known_relationships.add(key)
                changed = True

        if "dismissive" in lowered and "dismissive tone" not in story.triggers:
            story.triggers.append("dismissive tone")
            changed = True
        if "talked down to" in lowered and "being talked down to" not in story.triggers:
            story.triggers.append("being talked down to")
            changed = True

        for keyword, normalized in VALUE_KEYWORDS.items():
            if keyword in lowered and normalized not in story.values_observed:
                story.values_observed.append(normalized)
                changed = True

        for goal in _extract_list_signals(stripped, lowered, ("i want to ", "i'm trying to ", "i am trying to ", "working on ", "building ")):
            if goal not in story.current_chapter["active_goals"]:
                story.current_chapter["active_goals"].append(goal)
                changed = True

        for fear in _extract_list_signals(stripped, lowered, ("i'm afraid ", "i am afraid ", "i'm worried about ", "i am worried about ", "i fear ")):
            if fear not in story.current_chapter["active_fears"]:
                story.current_chapter["active_fears"].append(fear)
                changed = True

        if _looks_like_big_moment(lowered):
            event = stripped[:180]
            event_key = _event_key(event)
            if event not in known_events and event_key not in known_event_keys:
                big_moment_added = BigMoment(
                    date=datetime.now(timezone.utc).date().isoformat(),
                    event=event,
                    emotional_weight="high",
                    companion_was_there=True,
                )
                story.big_moments.append(big_moment_added)
                known_events.add(event)
                known_event_keys.add(event_key)
                changed = True

    recent_texts = [text.strip() for text in texts if text.strip()]
    if recent_texts:
        summary = " ".join(recent_texts[-3:])[:320].strip()
        if summary and story.current_chapter.get("summary") != summary:
            story.current_chapter["summary"] = summary
            changed = True
        mood_trend = mood_hint or infer_mood_trend(recent_texts[-1])
        if mood_trend and story.current_chapter.get("current_mood_trend") != mood_trend:
            story.current_chapter["current_mood_trend"] = mood_trend
            changed = True

    story.updated_at = observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return StoryUpdateResult(changed=changed, big_moment=big_moment_added)


def infer_mood_trend(text: str) -> str:
    lowered = text.casefold()
    if any(token in lowered for token in ("stress", "panic", "worried", "pressure", "overwhelmed")):
        return "stressed"
    if any(token in lowered for token in ("rough", "hurt", "alone", "invisible", "sad", "vent")):
        return "venting"
    if any(token in lowered for token in ("excited", "won", "happy", "launched", "celebrate")):
        return "celebrating"
    if any(token in lowered for token in ("meaning", "wondering", "thinking about", "late night")):
        return "reflective"
    return "neutral"


def _capture_after(original: str, lowered: str, marker: str) -> str | None:
    if marker not in lowered:
        return None
    start = lowered.index(marker) + len(marker)
    value = original[start:].strip()
    if not value:
        return None
    value = value.splitlines()[0]
    match = re.search(r"[.!?]", value)
    if match:
        value = value[: match.start()]
    return value[:120].strip(" ,.!?") or None


def _extract_relationship(text: str) -> dict[str, str] | None:
    patterns = (
        (r"\bmy (?P<role>friend|best friend|partner|boyfriend|girlfriend|wife|husband|manager|boss|coworker|cofounder|co-founder)\s+(?P<name>[A-Z][a-zA-Z'-]+)\b", None),
        (r"\b(?P<name>[A-Z][a-zA-Z'-]+)\s+is my (?P<role>friend|best friend|partner|manager|boss|coworker|cofounder|co-founder)\b", None),
    )
    for pattern, _ in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        role = match.group("role").replace("cofounder", "co-founder")
        return {"name": match.group("name"), "role": role, "notes": ""}
    return None


def _extract_list_signals(original: str, lowered: str, markers: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for marker in markers:
        if marker not in lowered:
            continue
        start = lowered.index(marker) + len(marker)
        value = original[start:].strip().strip(".")
        if not value:
            continue
        values.append(value[:140].strip(" ,.!?"))
    return values


def _looks_like_big_moment(lowered: str) -> bool:
    return any(token in lowered for token in BIG_MOMENT_PATTERNS)


def _extract_birthday(original: str, lowered: str) -> str | None:
    for marker in ("my birthday is ", "my birthday is on ", "birthday is "):
        value = _capture_after(original, lowered, marker)
        if value:
            return value
    return None


def _extract_upcoming_event(text: str) -> dict[str, str] | None:
    match = re.search(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b", text)
    if not match:
        return None
    lowered = text.casefold()
    if not any(token in lowered for token in ("event", "meeting", "interview", "deadline", "trip", "launch", "birthday")):
        return None
    date_value = match.group("date")
    title = text.strip()[:160]
    return {"date": date_value, "title": title, "notes": ""}


def _event_key(event_text: str) -> str:
    normalized = " ".join(event_text.casefold().split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:12]
