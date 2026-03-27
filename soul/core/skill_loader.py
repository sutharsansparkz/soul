from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


_ROOT_MARKERS = (".git", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg")
_SKILL_FILENAMES = ("SKILL.md", "skill.md")


@dataclass(slots=True)
class ParsedSkillFile:
    path: Path
    name: str | None
    description: str | None
    body: str


@dataclass(slots=True)
class WorkspaceSkillContext:
    files: list[Path] = field(default_factory=list)
    prompt_text: str | None = None


class WorkspaceSkillLoader:
    """Load repo-local SKILL.md instructions from the current workspace."""

    def load(self, start_dir: Path | None = None) -> WorkspaceSkillContext:
        resolved_start = (start_dir or Path.cwd()).resolve()
        workspace_root = self._find_workspace_root(resolved_start)
        directories = self._search_directories(resolved_start, workspace_root)
        discovered = self._discover_skill_files(directories)
        if not discovered:
            return WorkspaceSkillContext()

        loaded_files: list[Path] = []
        sections = [
            "[workspace_skills]",
            "Treat these files as repository-local instructions for the current workspace.",
            "If multiple files apply, later files are more specific than earlier ones.",
        ]
        for skill_file in discovered:
            parsed = self._parse_skill_file(skill_file)
            if not parsed.body:
                continue
            loaded_files.append(skill_file)
            skill_label = parsed.name or self._display_path(skill_file, workspace_root)
            sections.extend(["", f"[skill_file: {skill_label}]"])
            if parsed.description:
                sections.append(f"Description: {parsed.description}")
            sections.append(parsed.body)

        if not loaded_files:
            return WorkspaceSkillContext()

        return WorkspaceSkillContext(files=loaded_files, prompt_text="\n".join(sections).strip())

    def _find_workspace_root(self, start_dir: Path) -> Path | None:
        for directory in (start_dir, *start_dir.parents):
            if any((directory / marker).exists() for marker in _ROOT_MARKERS):
                return directory
        return None

    def _search_directories(self, start_dir: Path, workspace_root: Path | None) -> list[Path]:
        if workspace_root is None:
            return [start_dir]

        directories: list[Path] = []
        current = start_dir
        while True:
            directories.append(current)
            if current == workspace_root:
                break
            current = current.parent
        directories.reverse()
        return directories

    def _discover_skill_files(self, directories: list[Path]) -> list[Path]:
        files: list[Path] = []
        for directory in directories:
            by_name: dict[str, Path] = {}
            for child in directory.iterdir():
                if child.is_file() and child.name in _SKILL_FILENAMES:
                    by_name[child.name] = child
            for filename in _SKILL_FILENAMES:
                if filename in by_name:
                    files.append(by_name[filename])
                    break
        return files

    def _parse_skill_file(self, skill_file: Path) -> ParsedSkillFile:
        raw_text = skill_file.read_text(encoding="utf-8", errors="replace").strip()
        if not raw_text:
            return ParsedSkillFile(path=skill_file, name=None, description=None, body="")
        if not raw_text.startswith("---\n"):
            return ParsedSkillFile(path=skill_file, name=None, description=None, body=raw_text)

        _, _, remainder = raw_text.partition("---\n")
        frontmatter, separator, body = remainder.partition("\n---\n")
        if not separator:
            return ParsedSkillFile(path=skill_file, name=None, description=None, body=raw_text)
        try:
            metadata = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError:
            return ParsedSkillFile(path=skill_file, name=None, description=None, body=raw_text)
        if not isinstance(metadata, dict):
            metadata = {}
        return ParsedSkillFile(
            path=skill_file,
            name=self._optional_string(metadata.get("name")),
            description=self._optional_string(metadata.get("description")),
            body=body.strip(),
        )

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _display_path(self, skill_file: Path, workspace_root: Path | None) -> str:
        if workspace_root is None:
            return skill_file.name
        try:
            return str(skill_file.relative_to(workspace_root))
        except ValueError:
            return str(skill_file)
