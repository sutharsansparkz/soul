from __future__ import annotations

import argparse
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def _invoke(args: list[str]) -> int:
    os.environ["SOUL_SKIP_REACT_DISPATCH"] = "1"

    from soul.cli import app

    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    exit_code = 0

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            app(args=args, prog_name="soul", standalone_mode=False)
        except SystemExit as exc:
            try:
                exit_code = int(exc.code or 0)
            except Exception:
                exit_code = 1
        except Exception:  # pragma: no cover - defensive bridge error handling
            exit_code = 1
            traceback.print_exc()

    _emit(
        {
            "ok": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
        }
    )
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge for the React/Ink CLI frontend.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    invoke_parser = subparsers.add_parser("invoke")
    invoke_parser.add_argument("args", nargs=argparse.REMAINDER, help="CLI args to pass through.")

    parsed = parser.parse_args()
    if parsed.command == "invoke":
        args = list(parsed.args)
        if args[:1] == ["--"]:
            args = args[1:]
        return _invoke(args)

    _emit({"ok": False, "exit_code": 1, "stdout": "", "stderr": f"unknown command: {parsed.command}"})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
