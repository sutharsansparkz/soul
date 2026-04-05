from __future__ import annotations

import argparse
import json
import sys

from soul.bootstrap.errors import TurnExecutionError
from soul.cli_support.runtime import bootstrap
from soul.conversation.orchestrator import ConversationOrchestrator
from soul.maintenance.jobs import trigger_maintenance_if_due
from soul.memory.repositories.messages import MessagesRepository


def _emit(payload: dict[str, object], *, stream=sys.stdout) -> None:
    stream.write(json.dumps(payload, ensure_ascii=True))
    stream.write("\n")
    stream.flush()


def _start_session() -> int:
    settings, soul = bootstrap()
    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)
    session_id = messages_repo.create_session(soul.name)
    _emit({"ok": True, "session_id": session_id, "soul_name": soul.name})
    return 0


def _turn(session_id: str, user_input: str) -> int:
    settings, soul = bootstrap()
    orchestrator = ConversationOrchestrator(settings, soul)
    try:
        result = orchestrator.run_turn(session_id=session_id, user_text=user_input)
    except TurnExecutionError as exc:
        _emit({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1
    finally:
        orchestrator.shutdown()

    _emit(
        {
            "ok": True,
            "assistant_text": result.llm_result.text,
            "provider": result.llm_result.provider,
            "model": result.llm_result.model,
            "trace_id": result.trace_id,
            "mood": {
                "user_mood": result.mood.user_mood,
                "companion_state": result.mood.companion_state,
                "confidence": result.mood.confidence,
            },
        }
    )
    return 0


def _close_session(session_id: str) -> int:
    settings, _ = bootstrap()
    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)
    messages_repo.close_session(session_id)
    trigger_maintenance_if_due(settings)
    _emit({"ok": True})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Internal bridge used by the Ink chat UI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("start")

    turn_parser = subparsers.add_parser("turn")
    turn_parser.add_argument("--session-id", required=True)
    turn_parser.add_argument("--user-input", required=True)

    close_parser = subparsers.add_parser("close")
    close_parser.add_argument("--session-id", required=True)

    args = parser.parse_args()
    if args.command == "start":
        return _start_session()
    if args.command == "turn":
        return _turn(session_id=args.session_id, user_input=args.user_input)
    if args.command == "close":
        return _close_session(session_id=args.session_id)
    _emit({"ok": False, "error": f"unknown command: {args.command}"}, stream=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
