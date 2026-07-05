import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from loglens.pipeline.ingestion import stream_lines
from loglens.pipeline.parser import detect_format, parse_line
from loglens.pipeline.worker import run_worker_pool
from loglens.output.terminal import LiveProgress
from loglens.pipeline.detector import detect_anomalies, cluster_summary, DetectorConfig

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
    limit: int = typer.Option(20, "--limit", help="Max anomalies to display (default: 20)"),
    sort_by: str = typer.Option("severity", "--sort-by", help="Sort anomalies by: severity | time | service"),
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

        if not entries:
            console.print("[bold red]No valid log entries found.[/bold red]")
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

        console.print(f"[bold cyan][LogLens][/bold cyan] Computing embeddings for [bold]{len(entries):,}[/bold] entries...")
        vectors = engine.embed(entries)
        console.print(
            f"[bold cyan][LogLens][/bold cyan] Embeddings ready: "
            f"[bold green]shape={vectors.shape}[/bold green]"
        )

        # --- anomaly detection ---
        normal, anomalies, labels = detect_anomalies(entries, vectors)
        summary = cluster_summary(labels)

        # Use len(anomalies) — actual score-flagged count, not just noise points
        n_anomalies = len(anomalies)
        incident_flag = ""
        if n_anomalies > 0:
            severe = sum(1 for a in anomalies if a.level.upper() in ("EMERGENCY", "FATAL", "CRITICAL", "ERROR"))
            severe_pct = severe / len(entries)
            if severe_pct >= 0.30:
                incident_flag = " [bold red blink]⚠ INCIDENT[/bold red blink]"

        # --- category-wise breakdown ---
        CATEGORY_ORDER = ["EMERGENCY", "FATAL", "CRITICAL", "ERROR", "WARN", "WARNING", "NOTICE", "INFO", "DEBUG"]
        CATEGORY_COLOR = {
            "EMERGENCY": "bold red", "FATAL": "bold red", "CRITICAL": "bold red",
            "ERROR": "red", "WARN": "bold yellow", "WARNING": "bold yellow",
            "NOTICE": "yellow", "INFO": "dim", "DEBUG": "dim",
        }
        level_counts: dict = {}
        for a in anomalies:
            lvl = a.level.upper()
            level_counts[lvl] = level_counts.get(lvl, 0) + 1

        console.print(f"[bold cyan][LogLens][/bold cyan] Clusters found: [bold]{summary['clusters']}[/bold]")
        console.print(
            f"[bold cyan][LogLens][/bold cyan] Anomalies detected: "
            f"[bold red]{n_anomalies:,}[/bold red] 🚨{incident_flag}"
        )

        # print breakdown tree
        ordered_levels = [l for l in CATEGORY_ORDER if l in level_counts]
        # also catch any unexpected levels
        for l in level_counts:
            if l not in ordered_levels:
                ordered_levels.append(l)
        for idx, lvl in enumerate(ordered_levels):
            is_last = idx == len(ordered_levels) - 1
            branch = "└──" if is_last else "├──"
            color = CATEGORY_COLOR.get(lvl, "white")
            console.print(
                f"[bold cyan]          {branch}[/bold cyan] "
                f"[{color}]{lvl:<10}[/{color}] : [bold]{level_counts[lvl]:,}[/bold]"
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

        # --- severity ranking (suppress INFO false positives) ---
        LEVEL_WEIGHT = {"EMERGENCY": 6, "FATAL": 5, "CRITICAL": 5, "ERROR": 4, "WARN": 3, "WARNING": 3, "INFO": 1, "DEBUG": 0}

        def _severity(a):
            return LEVEL_WEIGHT.get(a.level.upper(), 2)

        # Filter out pure INFO anomalies unless they look genuinely bad
        _info_keywords = {"error", "fail", "timeout", "refused", "crash", "panic", "oom", "kill"}
        filtered_anomalies = [
            a for a in anomalies
            if a.level.upper() != "INFO" or any(kw in a.message.lower() for kw in _info_keywords)
        ]

        # Sort
        if sort_by == "severity":
            filtered_anomalies.sort(key=_severity, reverse=True)
        elif sort_by == "service":
            filtered_anomalies.sort(key=lambda a: a.service)
        # "time" = keep original order

        # --- display anomalies ---
        if filtered_anomalies:
            def _level_color(lvl: str) -> str:
                lvl = lvl.upper()
                if lvl in ("ERROR", "CRITICAL", "FATAL", "EMERGENCY"):
                    return "bold red"
                elif lvl in ("WARN", "WARNING"):
                    return "bold yellow"
                return "dim"

            display = filtered_anomalies[:limit]
            console.print()
            console.print(Panel(
                "\n".join(
                    f"[{_level_color(a.level)}] [{a.level}][/{_level_color(a.level)}] "
                    f"[yellow]{a.service}[/yellow] — {a.message[:120]}"
                    for a in display
                ),
                title=f"[bold red]ANOMALIES DETECTED ({len(filtered_anomalies)} total)[/bold red]",
                border_style="red",
            ))
            if len(filtered_anomalies) > limit:
                console.print(
                    f"[dim]... and {len(filtered_anomalies) - limit} more anomalies "
                    f"(use --limit {limit * 2} to see more)[/dim]"
                )
            suppressed = len(anomalies) - len(filtered_anomalies)
            if suppressed:
                console.print(f"[dim]{suppressed} INFO-level false positives suppressed[/dim]")
        else:
            console.print("\n[bold green] No anomalies detected![/bold green]")

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