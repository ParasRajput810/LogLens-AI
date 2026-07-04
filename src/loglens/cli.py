import asyncio
import typer
from rich.console import Console
from rich.table import Table
from loglens.pipeline.ingestion import stream_lines
from loglens.pipeline.parser import detect_format, parse_line

app = typer.Typer(
    name="loglens",
    help="LogLens AI Intelligent log analysis and anomaly detection",
    add_completion=False,
)

console = Console()

@app.command()
def version():
    console.print("[bold cyan]LogLens AI[/bold cyan] version [bold]0.1.0[/bold]")

@app.command()
def hello():
    console.print("[bold green] LogLens is alive![/bold green] Let's analyze some logs.")

@app.command()
def analyze(
    source: str = typer.Option(..., help="Log source: file path, URL, or stdin"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Stop after ingestion, show stats only"),
    verbose: bool = typer.Option(False, "--verbose", help="Show sample parsed entry"),
):
    async def _run():
        line_count = 0
        parsed_count = 0
        skipped_count = 0
        fmt = None
        sample_entry = None

        async for line in stream_lines(source):
            line_count += 1

            # detect format from first line
            if line_count == 1:
                fmt = detect_format(line)
                console.print(f"[bold cyan][LogLens][/bold cyan] Detected format: [yellow]{fmt}[/yellow]")

            entry = parse_line(line, fmt)
            if entry:
                parsed_count += 1
                if sample_entry is None:
                    sample_entry = entry
            else:
                skipped_count += 1

        console.print(f"[bold cyan][LogLens][/bold cyan] Lines read:   [bold]{line_count:,}[/bold]")
        console.print(f"[bold cyan][LogLens][/bold cyan] Parsed:       [bold green]{parsed_count:,}[/bold green]")
        console.print(f"[bold cyan][LogLens][/bold cyan] Skipped:      [bold red]{skipped_count}[/bold red]")

        if verbose and sample_entry:
            table = Table(title="Sample Parsed Entry")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")
            table.add_row("timestamp", sample_entry.timestamp)
            table.add_row("level", sample_entry.level)
            table.add_row("service", sample_entry.service)
            table.add_row("message", sample_entry.message)
            console.print(table)

        if dry_run:
            console.print("[bold cyan][LogLens][/bold cyan] --dry-run: stopping before processing.")

    asyncio.run(_run())

if __name__ == "__main__":
    app()