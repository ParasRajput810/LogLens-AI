import asyncio
import typer
from rich.console import Console
from loglens.pipeline.ingestion import stream_lines

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
):
    async def _run():
        line_count = 0
        console.print(f"[bold cyan][LogLens][/bold cyan] Source: [yellow]{source}[/yellow]")
        async for line in stream_lines(source):
            line_count += 1

        console.print(f"[bold cyan][LogLens][/bold cyan] Lines read: [bold]{line_count:,}[/bold]")
        if dry_run:
            console.print("[bold cyan][LogLens][/bold cyan] --dry-run: stopping before processing.")

    asyncio.run(_run())

if __name__ == "__main__":
    app()