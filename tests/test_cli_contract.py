from __future__ import annotations


CORE_COMMANDS = {
    "soul init",
    "soul chat",
    "soul memories",
    "soul story",
    "soul drift",
    "soul milestones",
    "soul status",
    "soul run-jobs",
    "soul skills",
    "soul db init",
    "soul db rebuild-fts",
    "soul config",
}

IN_SESSION_COMMANDS = {"/quit", "/save", "/mood", "/story", "/voice"}


def test_cli_surface_matches_the_spec():
    assert "soul init" in CORE_COMMANDS
    assert "soul chat" in CORE_COMMANDS
    assert "soul status" in CORE_COMMANDS
    assert "soul skills" in CORE_COMMANDS
    assert "soul db rebuild-fts" in CORE_COMMANDS
    assert len(CORE_COMMANDS) == 12


def test_in_session_commands_are_present():
    assert IN_SESSION_COMMANDS == {"/quit", "/save", "/mood", "/story", "/voice"}
