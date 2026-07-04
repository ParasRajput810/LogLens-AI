import asyncio
from typing import Callable, AsyncIterator
from loglens.models import LogEntry

async def run_worker_pool(
    entries: AsyncIterator[LogEntry],
    process_fn: Callable[[LogEntry], None],
    num_workers: int = 4,
    queue_size: int = 1000,
) -> dict:
    queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
    stats = {"processed": 0, "skipped": 0}

    async def producer():
        async for entry in entries:
            await queue.put(entry)
        for _ in range(num_workers):
            await queue.put(None)

    async def worker():
        while True:
            entry = await queue.get()
            if entry is None:
                queue.task_done()
                break
            try:
                process_fn(entry)
                stats["processed"] += 1
            except Exception:
                stats["skipped"] += 1
            finally:
                queue.task_done()

    await asyncio.gather(
        producer(),
        *[worker() for _ in range(num_workers)]
    )

    return stats