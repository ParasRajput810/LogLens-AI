import time
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.console import Console

class LiveProgress:
    def __init__(self, total: int = 0):
        self.total = total
        self.start_time = None
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TextColumn("[green]{task.completed:,}[/green] lines"),
            TimeElapsedColumn(),
            TextColumn("[yellow]{task.fields[speed]}[/yellow]"),
        )
        self.task_id = None

    def start(self):
        self.start_time = time.time()
        self.progress.start()
        self.task_id = self.progress.add_task(
            "Processing...", total=self.total, speed="0 lines/s"
        )

    def update(self, count: int):
        elapsed = time.time() - self.start_time
        speed = f"{count / elapsed:,.0f} lines/s" if elapsed > 0 else "0 lines/s"
        self.progress.update(self.task_id, completed=count, speed=speed)

    def stop(self):
        self.progress.stop()