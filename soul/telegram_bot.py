from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from soul.presence.telegram import TelegramBotRunner


app = typer.Typer(help="SOUL Telegram bot entrypoint.", add_completion=False)
console = Console()


@app.command()
def run() -> None:
    runner = TelegramBotRunner()
    status = runner.status()
    table = Table(title="SOUL Telegram Bot")
    table.add_column("Component")
    table.add_column("State")
    for key, value in status.items():
        table.add_row(key, value)
    console.print(table)

    if status["telegram"].startswith("disabled"):
        raise typer.Exit(code=0)

    runner.run_forever()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
