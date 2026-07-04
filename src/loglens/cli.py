import typer
from rich.console import Console

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

if __name__ == "__main__":
    app()