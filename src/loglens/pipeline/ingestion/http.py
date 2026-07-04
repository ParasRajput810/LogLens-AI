import aiohttp
from typing import AsyncIterator

class AsyncHTTPReader:
    def __init__(self, url: str):
        self.url = url

    async def __aiter__(self) -> AsyncIterator[str]:
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url) as response:
                response.raise_for_status()
                async for line in response.content:
                    yield line.decode("utf-8", errors="replace").rstrip("\n")