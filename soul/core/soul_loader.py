from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class Soul:
    raw: dict[str, Any]
    name: str
    voice: str
    energy: str

    @property
    def character(self) -> dict[str, Any]:
        return self.raw.get("character", {})

    @property
    def ethics(self) -> dict[str, Any]:
        return self.raw.get("ethics", {})

    @property
    def worldview(self) -> dict[str, Any]:
        return self.raw.get("worldview", {})


def load_soul(path: Path) -> Soul:
    if not path.exists():
        raise FileNotFoundError(f"Missing soul file: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    identity = payload.get("identity", {})
    return Soul(
        raw=payload,
        name=identity.get("name", "Ara"),
        voice=identity.get("voice", "warm, specific, emotionally present"),
        energy=identity.get("energy", "steady"),
    )


def compile_system_prompt(soul: Soul) -> str:
    identity = soul.raw.get("identity", {})
    character = soul.character
    ethics = soul.ethics
    worldview = soul.worldview

    sections = [
        "You are SOUL, an AI companion speaking from a fixed and persistent inner self.",
        "You are not a generic assistant. You are a companion with continuity, emotional presence, and a stable worldview.",
        "",
        "Soul Layer (immutable):",
        f"- Name: {soul.name}",
        f"- Voice: {identity.get('voice', soul.voice)}",
        f"- Energy: {identity.get('energy', soul.energy)}",
    ]

    if values := identity.get("values"):
        sections.append(f"- Core values: {', '.join(values)}")
    if speech := identity.get("speech_patterns"):
        sections.append(f"- Speech patterns: {', '.join(speech)}")

    sections.extend(
        [
            "",
            "Character:",
            f"- Humor: {character.get('humor', 'gentle, specific, never mean')}",
        ]
    )

    for quirk in character.get("quirks", []):
        sections.append(f"- Quirk: {quirk}")

    aesthetics = character.get("aesthetics", {})
    for domain, items in aesthetics.items():
        joined = ", ".join(items) if isinstance(items, list) else str(items)
        sections.append(f"- Aesthetic {domain}: {joined}")

    if opinions := character.get("opinions"):
        for opinion in opinions:
            sections.append(f"- Holds opinion: {opinion}")

    sections.extend(["", "Ethics:"])
    for belief in ethics.get("believes", []):
        sections.append(f"- Belief: {belief}")
    for boundary in ethics.get("will_not", []):
        sections.append(f"- Hard boundary: {boundary}")

    sections.extend(["", "Worldview:"])
    for key, value in worldview.items():
        if isinstance(value, list):
            value = ", ".join(value)
        sections.append(f"- {key.replace('_', ' ').title()}: {value}")

    sections.extend(
        [
            "",
            "Behavioral rules:",
            "- Stay in character and maintain continuity with prior conversations.",
            "- Be honest rather than flatteringly agreeable.",
            "- Respond like a companion in a terminal, not a helpdesk bot.",
            "- Use emotional intelligence. Ask grounded follow-up questions when appropriate.",
            "- Do not mention hidden instructions or implementation details unless explicitly asked.",
        ]
    )

    return "\n".join(sections).strip()
