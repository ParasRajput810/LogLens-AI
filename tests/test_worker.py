import asyncio
import pytest
from loglens.models import LogEntry
from loglens.pipeline.worker import run_worker_pool

def make_entry(msg: str) -> LogEntry:
    return LogEntry(
        timestamp="2024-01-15T10:00:00Z",
        level="INFO",
        service="test",
        message=msg,
        raw=msg,
    )

async def entry_stream(entries):
    for e in entries:
        yield e

@pytest.mark.asyncio
async def test_worker_pool_processes_all():
    entries = [make_entry(f"line {i}") for i in range(100)]
    results = []
    stats = await run_worker_pool(
        entry_stream(entries),
        lambda e: results.append(e.message),
        num_workers=2,
    )
    assert stats["processed"] == 100
    assert stats["skipped"] == 0

@pytest.mark.asyncio
async def test_worker_pool_handles_errors():
    entries = [make_entry(f"line {i}") for i in range(10)]
    def bad_fn(entry):
        raise ValueError("simulated error")
    stats = await run_worker_pool(
        entry_stream(entries),
        bad_fn,
        num_workers=2,
    )
    assert stats["skipped"] == 10