import pytest

from kovo_searcher.engine import SearchError, SearchResult, _normalise, _safe_url, _score, search


def test_normalise_deduplicates_and_rejects_unsafe_urls():
    rows = [
        {"title": "One", "href": "https://example.com/a#part", "body": "text"},
        {"title": "Duplicate", "href": "https://example.com/a", "body": "text"},
        {"title": "Local", "href": "http://127.0.0.1", "body": "no"},
        {"title": "Bad", "href": "javascript:alert(1)", "body": "no"},
    ]
    results = _normalise(rows, 10)
    assert len(results) == 1
    assert results[0].url == "https://example.com/a"


def test_score_ranks_title_matches_first():
    results = [
        SearchResult(1, "Unrelated page", "https://a.com", "other"),
        SearchResult(2, "Python asyncio guide", "https://b.com", "tasks"),
    ]
    ranked = _score("Python asyncio", results)
    assert ranked[0].url == "https://b.com"
    assert ranked[0].rank == 1


def test_sync_helper_rejects_running_loop():
    import asyncio
    from kovo_searcher.engine import search_sync

    async def run():
        with pytest.raises(SearchError, match="await search"):
            search_sync("query")

    asyncio.run(run())


@pytest.mark.asyncio
async def test_search_uses_provider_and_returns_results(monkeypatch):
    import kovo_searcher.engine as engine

    def fake_provider(*args):
        return [{"title": "Python", "href": "https://python.org", "body": "Python docs"}]

    monkeypatch.setattr(engine, "_provider_search", fake_provider)
    engine.clear_cache()
    results = await search("Python", use_cache=False)
    assert results[0].title == "Python"
