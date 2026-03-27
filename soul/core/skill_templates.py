from __future__ import annotations

from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True, slots=True)
class BuiltinSkillTemplate:
    name: str
    description: str
    resource_path: str


_BUILTIN_SKILL_TEMPLATES: dict[str, BuiltinSkillTemplate] = {
    "file-explorer": BuiltinSkillTemplate(
        name="file-explorer",
        description="Read-only workspace exploration mode for inspecting files, modules, data flow, and likely edit targets.",
        resource_path="templates/skills/file-explorer/SKILL.md",
    ),
}


def list_builtin_skill_templates() -> list[BuiltinSkillTemplate]:
    return sorted(_BUILTIN_SKILL_TEMPLATES.values(), key=lambda item: item.name)


def get_builtin_skill_template(name: str) -> BuiltinSkillTemplate | None:
    return _BUILTIN_SKILL_TEMPLATES.get(name)


def read_builtin_skill_template(name: str) -> str:
    template = get_builtin_skill_template(name)
    if template is None:
        raise KeyError(name)
    return resources.files("soul").joinpath(template.resource_path).read_text(encoding="utf-8")
