import aiofiles
from typing import AsyncIterator

CHUNK_LINES = 1000 

class AsyncFileReader:
    def __init__(self, path: str):
        self.path = path

    async def __aiter__(self) -> AsyncIterator[str]:
        async with aiofiles.open(self.path, mode="r", errors="replace") as f:
            async for line in f:
                yield line.rstrip("\n")