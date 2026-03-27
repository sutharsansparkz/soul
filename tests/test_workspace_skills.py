from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from soul import db
import soul.cli as cli
from soul.config import Settings
from soul.conversation.orchestrator import ConversationOrchestrator
from soul.core.context_builder import ContextBuilder, ContextBundle
from soul.core.skill_loader import WorkspaceSkillLoader
from soul.core.skill_templates import read_builtin_skill_template
from soul.core.llm_client import LLMResult
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul
from soul.observability.traces import TurnTraceRepository


def _settings(tmp_path) -> Settings:  # noqa: ANN001
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="test-user",
    )


def _soul() -> Soul:
    return Soul(
        raw={
            "identity": {"name": "Ara", "voice": "warm", "energy": "steady"},
            "character": {},
            "ethics": {},
            "worldview": {},
        },
        name="Ara",
        voice="warm",
        energy="steady",
    )


def test_context_builder_loads_workspace_skill_files_from_root_to_leaf(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    nested = workspace / "packages" / "api"
    nested.mkdir(parents=True)
    (workspace / "pyproject.toml").write_text("[project]\nname='workspace'\n", encoding="utf-8")
    (workspace / "skill.md").write_text(
        "---\nname: root-skill\ndescription: Root workspace guidance.\n---\nRoot skill: prefer migration-safe changes.\n",
        encoding="utf-8",
    )
    (workspace / "packages" / "SKILL.md").write_text(
        "---\nname: package-skill\ndescription: Package-specific guidance.\n---\nPackage skill: preserve API compatibility.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(nested)

    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    session_id = db.create_session(settings.database_url, "Ara")
    builder = ContextBuilder(settings, _soul())
    mood = MoodSnapshot(user_mood="curious", companion_state="curious", confidence=0.9, rationale="test")

    bundle = builder.build(session_id=session_id, user_input="add a feature", mood=mood)
    prompt = bundle.system_prompt

    assert "workspace_skill" in bundle.prompt_sections
    assert "[workspace_skills]" in prompt
    assert prompt.index("You are SOUL") < prompt.index("[workspace_skills]")
    assert "[skill_file: root-skill]" in prompt
    assert "Description: Root workspace guidance." in prompt
    assert "[skill_file: package-skill]" in prompt
    assert "Description: Package-specific guidance." in prompt
    assert prompt.index("Root skill: prefer migration-safe changes.") < prompt.index(
        "Package skill: preserve API compatibility."
    )
    assert "name: root-skill" not in prompt
    assert "description: Root workspace guidance." not in prompt
    assert bundle.workspace_skill_files == [
        str((workspace / "skill.md").resolve()),
        str((workspace / "packages" / "SKILL.md").resolve()),
    ]


def test_run_turn_writes_workspace_skill_files_to_trace(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)
    session_id = db.create_session(settings.database_url, "Ara")
    orchestrator = ConversationOrchestrator(settings, _soul())
    mood = MoodSnapshot(
        user_mood="reflective",
        companion_state="reflective",
        confidence=0.8,
        rationale="test mood",
    )

    class ImmediateFuture:
        def result(self, timeout=None):  # noqa: ANN001, ARG002
            return {"persisted_records": {}}

    monkeypatch.setattr(orchestrator.mood_engine, "analyze", lambda *args, **kwargs: mood)
    monkeypatch.setattr(
        orchestrator.context_loader,
        "load",
        lambda *args, **kwargs: ContextBundle(
            system_prompt="system",
            messages=[],
            story_summary=None,
            memory_snippets=[],
            retrieved_memories=[],
            prompt_sections=["mood", "soul_prompt", "workspace_skill"],
            workspace_skill_files=["/tmp/workspace/SKILL.md"],
        ),
    )
    monkeypatch.setattr(
        orchestrator.client,
        "reply",
        lambda **kwargs: LLMResult(
            text="I heard you.",
            provider="mock-openai",
            model="test-model",
            fallback_used=False,
        ),
    )
    monkeypatch.setattr(
        orchestrator.post_processor,
        "process_turn_background",
        lambda **kwargs: ImmediateFuture(),
    )

    result = orchestrator.run_turn(session_id=session_id, user_text="follow the repo skill")
    trace = TurnTraceRepository(settings.database_url, user_id=settings.user_id).get_trace(result.trace_id)

    assert trace is not None
    assert trace["trace"]["workspace_skill_files"] == ["/tmp/workspace/SKILL.md"]
    assert trace["trace"]["prompt_sections"] == ["mood", "soul_prompt", "workspace_skill"]


def test_workspace_skill_loader_leaves_invalid_frontmatter_as_body(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    skill_file = workspace / "SKILL.md"
    skill_file.write_text("---\nname: [broken\n---\nKeep the raw text.\n", encoding="utf-8")

    parsed = WorkspaceSkillLoader()._parse_skill_file(skill_file)

    assert parsed.name is None
    assert parsed.description is None
    assert parsed.body.startswith("---\nname: [broken")


def test_builtin_file_explorer_skill_has_required_metadata():
    raw_text = read_builtin_skill_template("file-explorer")
    frontmatter, separator, _ = raw_text.removeprefix("---\n").partition("\n---\n")

    assert raw_text.startswith("---\n")
    assert separator == "\n---\n"
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == "file-explorer"
    assert "Read-only workspace exploration mode" in metadata["description"]
    assert "Do not create, edit, rename, or delete files." in raw_text


def test_skills_init_writes_builtin_template_to_target_directory(tmp_path):
    target = tmp_path / "workspace"

    result = CliRunner().invoke(cli.app, ["skills", "init", "file-explorer", "--dir", str(target)])

    assert result.exit_code == 0
    skill_file = target / "SKILL.md"
    assert skill_file.exists()
    assert skill_file.read_text(encoding="utf-8") == read_builtin_skill_template("file-explorer")


def test_skills_init_rejects_existing_skill_without_force(tmp_path):
    target = tmp_path / "workspace"
    target.mkdir()
    skill_file = target / "SKILL.md"
    skill_file.write_text("existing", encoding="utf-8")

    result = CliRunner().invoke(cli.app, ["skills", "init", "file-explorer", "--dir", str(target)])

    assert result.exit_code == 1
    assert "Refusing to overwrite existing file" in result.stdout
    assert skill_file.read_text(encoding="utf-8") == "existing"
