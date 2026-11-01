from types import SimpleNamespace

import pytest

from kovo_searcher.engine import SearchError
import kovo_searcher.browser as browser_module


def test_extract_sources_keeps_unique_public_http_links():
    answer = (
        "See [Python](https://python.org/) and https://example.com/docs. "
        "Ignore javascript:alert(1) and http://127.0.0.1/private."
    )
    sources = browser_module._extract_sources(answer)
    assert [item["url"] for item in sources] == [
        "https://python.org/",
        "https://example.com/docs",
    ]
    assert sources[0]["title"] == "Python"


def test_validate_options_rejects_bad_values():
    with pytest.raises(SearchError, match="Query cannot be empty"):
        browser_module._validate_options("  ", 8, 120)
    with pytest.raises(SearchError, match="max_steps"):
        browser_module._validate_options("test", 0, 120)
    with pytest.raises(SearchError, match="timeout"):
        browser_module._validate_options("test", 8, 0)


def test_build_llm_prefers_browser_use_key(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("KOVO_MODEL_PROVIDER", raising=False)
    fake = SimpleNamespace(ChatBrowserUse=lambda **kwargs: ("browser-llm", kwargs["model"]))

    llm, model, provider = browser_module._build_llm(fake)

    assert llm == ("browser-llm", "bu-2-0")
    assert model == "bu-2-0"
    assert provider == "browser-use"


@pytest.mark.asyncio
async def test_browse_runs_agent_and_returns_sources(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")
    captured = {}

    class FakeBrowser:
        def __init__(self, *, use_cloud=False):
            captured["use_cloud"] = use_cloud

    class FakeHistory:
        def final_result(self):
            return "A useful answer. Source: [Example](https://example.com/page)."

    class FakeAgent:
        def __init__(self, *, task, llm, browser):
            captured["task"] = task
            captured["browser"] = browser

        async def run(self, *, max_steps):
            captured["max_steps"] = max_steps
            return FakeHistory()

    fake = SimpleNamespace(
        Browser=FakeBrowser,
        Agent=FakeAgent,
        ChatBrowserUse=lambda **kwargs: SimpleNamespace(model=kwargs["model"]),
    )
    monkeypatch.setattr(browser_module, "_load_browser_use", lambda: fake)

    result = await browser_module.browse("Research a topic", max_steps=4, use_cloud=False)

    assert result.query == "Research a topic"
    assert result.sources == [{"title": "Example", "url": "https://example.com/page"}]
    assert captured["max_steps"] == 4
    assert captured["use_cloud"] is False
    assert "read-only research" in captured["task"]


@pytest.mark.asyncio
async def test_browse_times_out(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")

    class FakeBrowser:
        def __init__(self, **kwargs):
            pass

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        async def run(self, **kwargs):
            import asyncio
            await asyncio.sleep(0.05)

    fake = SimpleNamespace(
        Browser=FakeBrowser,
        Agent=FakeAgent,
        ChatBrowserUse=lambda **kwargs: object(),
    )
    monkeypatch.setattr(browser_module, "_load_browser_use", lambda: fake)

    with pytest.raises(SearchError, match="timeout"):
        await browser_module.browse("Research", timeout=0.001)
