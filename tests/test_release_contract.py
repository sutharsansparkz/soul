from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_release_workflow_uses_main_only_semantic_release_flow():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "name: Semantic Release" in workflow
    assert "workflow_dispatch:" in workflow
    assert "group: semantic-release" in workflow
    assert "actions/checkout@v5" in workflow
    assert 'python-version: "3.11"' in workflow
    assert "actions/setup-python@v6" in workflow
    assert "git reset --hard ${{ github.sha }}" in workflow
    assert "python-semantic-release/python-semantic-release@v10.5.3" in workflow
    assert "python-semantic-release/publish-action@v10.5.3" in workflow
    assert "if: steps.release.outputs.released == 'true'" in workflow
    assert "path: dist" in workflow
    assert "github.ref_name" in workflow


def test_semantic_release_config_tracks_main_branch_versions_and_changelog():
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'commit_parser = "conventional"' in config
    assert 'tag_format = "v{version}"' in config
    assert '[tool.semantic_release.branches.main]' in config
    assert 'match = "^main$"' in config
    assert 'parse_squash_commits = true' in config
    assert 'ignore_merge_commits = true' in config
    assert '[tool.semantic_release.changelog]' in config
    assert 'mode = "update"' in config
    assert 'insertion_flag = "<!-- version list -->"' in config
    assert 'changelog_file = "CHANGELOG.md"' in config
    assert "chore\\(release\\): .+" in config


def test_changelog_exists_and_is_ready_for_semantic_release_updates():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert changelog.startswith("# CHANGELOG")
    assert "<!-- version list -->" in changelog
    assert "## v0.6.2" in changelog
