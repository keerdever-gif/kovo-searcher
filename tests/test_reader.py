import pytest

from kovo_searcher import PageContent
from kovo_searcher.reader import open_page


class FakeContent:
    async def read(self, n=-1):
        return b"<html><head><title>Demo</title><meta name='description' content='A page'></head><body><nav>menu</nav><main><h1>Hello</h1><p>World</p></main></body></html>"


class FakeResponse:
    status = 200
    headers = {"Content-Type": "text/html; charset=utf-8"}
    content_length = None
    charset = "utf-8"
    url = "https://example.com/"
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    content = FakeContent()


class FakeSession:
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    def get(self, *args, **kwargs): return FakeResponse()


@pytest.mark.asyncio
async def test_open_page_extracts_main_content(monkeypatch):
    import kovo_searcher.reader as reader
    monkeypatch.setattr(reader.aiohttp, "ClientSession", FakeSession)
    monkeypatch.setattr(reader, "_public_host", lambda host: _true())
    page = await open_page("https://example.com")
    assert isinstance(page, PageContent)
    assert page.title == "Demo"
    assert "Hello World" in page.text
    assert "menu" not in page.text


async def _true():
    return True
