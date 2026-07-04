import sys
import asyncio
from typing import AsyncIterator

class AsyncStdinReader:
    async def __aiter__(self) -> AsyncIterator[str]:
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            yield line.rstrip("\n")