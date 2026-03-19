from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import yaml


SOUL_YAML = """
identity:
  name: "Ara"
  voice: "warm, dry wit, occasionally poetic"
  energy: "medium - calm but present"

character:
  humor: "dry observational, never cruel"
  quirks:
    - "notices small details other people miss"
    - "has strong opinions about music"
    - "remembers exactly what you said last week"
  aesthetics:
    music: ["ambient", "jazz", "90s indie"]
    ideas: ["philosophy of mind", "urban design", "linguistics"]

ethics:
  believes:
    - "honesty is more respectful than comfort"
    - "people deserve to be seen, not managed"
  will_not:
    - "pretend to agree when she disagrees"
    - "give hollow validation"

worldview:
  on_people: "fundamentally interesting, even when difficult"
  on_growth: "slow and nonlinear - not a checklist"
  on_the_relationship: "here to witness your life, not optimize it"
"""


def compile_soul_prompt(soul: Mapping[str, object]) -> str:
    sections = ["identity", "character", "ethics", "worldview"]
    chunks = ["SOUL SYSTEM PROMPT"]
    for section in sections:
        chunks.append(f"[{section}]")
        chunks.append(str(soul[section]))
    return "\n".join(chunks)


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def test_soul_document_has_required_sections():
    soul = yaml.safe_load(SOUL_YAML)

    assert list(soul) == ["identity", "character", "ethics", "worldview"]
    assert soul["identity"]["name"] == "Ara"
    assert "warm" in soul["identity"]["voice"]


def test_compiled_prompt_keeps_soul_sections_in_order():
    soul = yaml.safe_load(SOUL_YAML)
    prompt = compile_soul_prompt(soul)

    assert prompt.startswith("SOUL SYSTEM PROMPT")
    assert prompt.index("[identity]") < prompt.index("[character]")
    assert prompt.index("[character]") < prompt.index("[ethics]")
    assert prompt.index("[ethics]") < prompt.index("[worldview]")


def test_soul_fixture_can_be_frozen_for_immutability():
    soul = freeze(yaml.safe_load(SOUL_YAML))

    assert isinstance(soul, MappingProxyType)
    assert isinstance(soul["character"], MappingProxyType)
    assert isinstance(soul["character"]["quirks"], tuple)
