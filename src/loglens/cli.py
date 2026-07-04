import asyncio
import typer
from rich.console import Console
from rich.table import Table
from loglens.pipeline.ingestion import stream_lines
from loglens.pipeline.parser import detect_format, parse_line
from loglens.pipeline.worker import run_worker_pool
from loglens.output.terminal import LiveProgress

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
    workers: int = typer.Option(4, "--workers", help="Number of parallel workers"),
    deep: bool = typer.Option(False, "--deep", help="Use neural embeddings (accurate, slower)"),
):
    async def _run():
        line_count = 0
        fmt = None
        sample_entry = None
        entries = []

        console.print(f"\n[bold cyan][LogLens][/bold cyan] Source: [yellow]{source}[/yellow]")
        async for line in stream_lines(source):
            line_count += 1
            if line_count == 1:
                fmt = detect_format(line)
                console.print(f"[bold cyan][LogLens][/bold cyan] Detected format: [yellow]{fmt}[/yellow]")

            entry = parse_line(line, fmt)
            if entry:
                if sample_entry is None:
                    sample_entry = entry
                entries.append(entry)

        console.print(f"[bold cyan][LogLens][/bold cyan] Lines ingested: [bold]{line_count:,}[/bold]")

        if dry_run:
            console.print("[bold cyan][LogLens][/bold cyan] --dry-run: stopping before processing.")
            return

        if deep:
            console.print("[bold cyan][LogLens][/bold cyan] Mode: [bold magenta] Deep (neural embeddings)[/bold magenta]")
            try:
                from loglens.pipeline.deep_embeddings import DeepEmbeddingEngine
                engine = DeepEmbeddingEngine()
            except ImportError:
                console.print(
                    "[bold red]Deep mode requires sentence-transformers.[/bold red]\n"
                    "Install with: [yellow]pip install sentence-transformers[/yellow]"
                )
                raise typer.Exit(code=1)
        else:
            console.print("[bold cyan][LogLens][/bold cyan] Mode: [bold green] Fast (TF-IDF embeddings)[/bold green]")
            from loglens.pipeline.embeddings import EmbeddingEngine
            engine = EmbeddingEngine()

        if entries:
            console.print(f"[bold cyan][LogLens][/bold cyan] Computing embeddings for [bold]{len(entries):,}[/bold] entries...")
            vectors = engine.embed(entries)
            console.print(
                f"[bold cyan][LogLens][/bold cyan] Embeddings ready: "
                f"[bold green]shape={vectors.shape}[/bold green]"
            )

        # --- worker pool ---
        progress = LiveProgress(total=len(entries))
        processed_count = 0

        def process_fn(entry):
            nonlocal processed_count
            processed_count += 1
            progress.update(processed_count)

        progress.start()

        async def entry_stream():
            for e in entries:
                yield e

        stats = await run_worker_pool(
            entry_stream(),
            process_fn,
            num_workers=workers,
        )

        progress.stop()

        console.print(f"\n[bold cyan][LogLens][/bold cyan] Processed: [bold green]{stats['processed']:,}[/bold green]")
        console.print(f"[bold cyan][LogLens][/bold cyan] Skipped:   [bold red]{stats['skipped']}[/bold red]")

        if verbose and sample_entry:
            table = Table(title="Sample Parsed Entry")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")
            table.add_row("timestamp", sample_entry.timestamp)
            table.add_row("level", sample_entry.level)
            table.add_row("service", sample_entry.service)
            table.add_row("message", sample_entry.message)
            console.print(table)

    asyncio.run(_run())

if __name__ == "__main__":
    app()