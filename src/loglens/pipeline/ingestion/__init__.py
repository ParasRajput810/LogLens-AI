from .file import AsyncFileReader
from .stdin import AsyncStdinReader
from .http import AsyncHTTPReader
from typing import AsyncIterator

def get_reader(source: str) -> AsyncFileReader | AsyncStdinReader | AsyncHTTPReader:
    if source == "stdin":
        return AsyncStdinReader()
    elif source.startswith("http://") or source.startswith("https://"):
        return AsyncHTTPReader(source)
    else:
        return AsyncFileReader(source)

async def stream_lines(source: str) -> AsyncIterator[str]:
    reader = get_reader(source)
    async for line in reader:
        yield line