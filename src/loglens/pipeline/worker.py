from __future__ import annotations

import asyncio
import logging
from collections import Counter
from concurrent.futures import Executor
from typing import AsyncIterator, Callable, Optional

from loglens.models import LogEntry

logger = logging.getLogger("loglens.worker")


async def run_worker_pool(
    entries: AsyncIterator[LogEntry],
    process_fn: Callable[[LogEntry], object],
    num_workers: int = 4,
    queue_size: int = 1000,
    executor: Optional[Executor] = None,
    on_progress: Optional[Callable[[int], None]] = None,
    progress_every: int = 100,
    debug: bool = False,
) -> dict:

    queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
    stats: dict = {"processed": 0, "skipped": 0, "errors": Counter()}
    loop = asyncio.get_running_loop()

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
                await loop.run_in_executor(executor, process_fn, entry)
                stats["processed"] += 1
                if on_progress and stats["processed"] % progress_every == 0:
                    on_progress(stats["processed"])
            except Exception as e:                       
                stats["skipped"] += 1
                stats["errors"][type(e).__name__] += 1
                logger.debug("entry skipped: %s: %s", type(e).__name__, e)
                if debug:
                    raise
            finally:
                queue.task_done()

    await asyncio.gather(producer(), *[worker() for _ in range(num_workers)])

    stats["errors"] = dict(stats["errors"])
    if on_progress:
        on_progress(stats["processed"])
    return stats