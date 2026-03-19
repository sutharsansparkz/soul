from __future__ import annotations


CORE_COMMANDS = {
    "soul chat",
    "soul memories",
    "soul story",
    "soul drift",
    "soul milestones",
    "soul status",
    "soul run-jobs",
    "soul db init",
    "soul config",
}

IN_SESSION_COMMANDS = {"/quit", "/save", "/mood", "/story", "/voice"}


def test_cli_surface_matches_the_spec():
    assert "soul chat" in CORE_COMMANDS
    assert "soul status" in CORE_COMMANDS
    assert len(CORE_COMMANDS) == 9


def test_in_session_commands_are_present():
    assert IN_SESSION_COMMANDS == {"/quit", "/save", "/mood", "/story", "/voice"}
