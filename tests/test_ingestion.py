import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock
from loglens.pipeline.ingestion import get_reader, stream_lines
from loglens.pipeline.ingestion.file import AsyncFileReader
from loglens.pipeline.ingestion.stdin import AsyncStdinReader
from loglens.pipeline.ingestion.http import AsyncHTTPReader



def test_get_reader_returns_file_reader():
    reader = get_reader("tests/fixtures/sample.log")
    assert isinstance(reader, AsyncFileReader)

def test_get_reader_returns_stdin_reader():
    reader = get_reader("stdin")
    assert isinstance(reader, AsyncStdinReader)

def test_get_reader_returns_http_reader():
    reader = get_reader("https://example.com/app.log")
    assert isinstance(reader, AsyncHTTPReader)


@pytest.mark.asyncio
async def test_file_reader_streams_lines():
    content = "\n".join([f"INFO [service] log line {i}" for i in range(100)])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        lines = []
        async for line in AsyncFileReader(tmp_path):
            lines.append(line)
        assert len(lines) == 100
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_http_reader_mocked():
    fake_lines = [b"INFO [nginx] GET /api 200\n", b"ERROR [app] timeout\n"]

    async def fake_content():
        for line in fake_lines:
            yield line

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content.__aiter__ = lambda self: fake_content()

    mock_session = MagicMock()
    mock_session.get = MagicMock()
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("loglens.pipeline.ingestion.http.aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        lines = []
        async for line in AsyncHTTPReader("https://fake-url.com/app.log"):
            lines.append(line)

    assert len(lines) == 2
    assert "GET /api 200" in lines[0]