"""llmobs CLI (spec §9).

Commands are filled in milestone by milestone. `serve` lands in M4 (gateway),
`report` in M6 (reporter), `pricing` in M3.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from llmobs import __version__
from llmobs.config import Config
from llmobs.recording import EventStore, Recorder

app = typer.Typer(
    add_completion=False,
    help="LLM observability: local, portable, and decoupled from your business logic.",
)


def _pending(command: str, milestone: str) -> None:
    typer.secho(
        f"`llmobs {command}` is not implemented yet (lands in {milestone}).",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show the version and exit."),
) -> None:
    if version:
        typer.echo(f"llmobs {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def serve(
    port: int = typer.Option(None, help="Gateway port (default 8900)."),
    data_dir: Path = typer.Option(None, help="Data directory (default ./data)."),
    capture_bodies: bool = typer.Option(
        False, help="Store prompt/response bodies (opt-in, local debugging only)."
    ),
) -> None:
    """Start the proxy that intercepts and measures LLM calls."""
    Config.load(port=port, data_dir=data_dir, capture_bodies=capture_bodies or None)
    _pending("serve", "M4 (gateway)")


@app.command()
def report(
    since: str = typer.Option(None, help="From date (dd-mm-yyyy)."),
    until: str = typer.Option(None, help="To date (dd-mm-yyyy)."),
    project: str = typer.Option(None, help="Filter by project."),
    agent: str = typer.Option(None, help="Filter by agent."),
    out: Path = typer.Option(None, help="Output directory (default ./data/reports)."),
) -> None:
    """Generate metrics.json + report.md for cost and consumption."""
    _pending("report", "M6 (reporter)")


@app.command()
def pricing(
    check: bool = typer.Option(False, "--check", help="Validate pricing.yaml and list models."),
) -> None:
    """Inspect the pricing table."""
    _pending("pricing", "M3 (pricing engine)")


@app.command()
def rebuild(
    data_dir: Path = typer.Option(None, help="Data directory (default ./data)."),
) -> None:
    """Rebuild the SQLite database from events.jsonl (the source of truth)."""
    config = Config.load(data_dir=data_dir)
    with EventStore(config.db_path) as store:
        n = store.rebuild_from_jsonl(config.jsonl_path)
    typer.secho(f"OK - Rebuilt {n} events from {config.jsonl_path}", fg=typer.colors.GREEN)


@app.command()
def status(
    data_dir: Path = typer.Option(None, help="Data directory (default ./data)."),
) -> None:
    """Show how many events have been recorded."""
    config = Config.load(data_dir=data_dir)
    with Recorder(config.data_dir) as recorder:
        typer.echo(f"data_dir : {config.data_dir}")
        typer.echo(f"events   : {recorder.store.count()}")


def main() -> None:
    # The Windows console defaults to cp1252 and raises UnicodeEncodeError on accented
    # characters or glyphs. Force UTF-8 before emitting anything.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    app()


if __name__ == "__main__":
    main()
