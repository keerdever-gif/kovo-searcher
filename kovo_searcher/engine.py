from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import random
import re
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

MAX_QUERY_CHARS = 500
MAX_RESULTS = 20
DEFAULT_TIMEOUT = 15.0
DEFAULT_CACHE_TTL = 120.0
_LOG = logging.getLogger("kovo_searcher")
_CACHE: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
_CACHE_LOCK = threading.Lock()


class SearchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {"error": {"code": self.code, "message": self.message}}


@dataclass(slots=True)
class SearchResult:
    rank: int
    title: str
    url: str
    snippet: str
    score: float = 0.0
    source: str = "duckduckgo"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_rag_document(self) -> dict[str, Any]:
        return {
            "id": hashlib.sha256(self.url.encode()).hexdigest(),
            "text": "\n".join(part for part in (self.title, self.snippet) if part),
            "metadata": {
                "title": self.title,
                "url": self.url,
                "rank": self.rank,
                "score": self.score,
                "source": self.source,
            },
        }


def _validate_query(query: str, max_results: int) -> tuple[str, int]:
    if not isinstance(query, str) or not query.strip():
        raise SearchError("invalid_query", "Query cannot be empty.")
    query = " ".join(query.split())
    if len(query) > MAX_QUERY_CHARS:
        raise SearchError("invalid_query", f"Query exceeds {MAX_QUERY_CHARS} characters.")
    if isinstance(max_results, bool) or not isinstance(max_results, int) or max_results < 1:
        raise SearchError("invalid_max_results", "max_results must be an integer >= 1.")
    return query, min(max_results, MAX_RESULTS)


def _safe_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            return None
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                return None
        except ValueError:
            pass
        port = parsed.port
        netloc = host if port is None else f"{host}:{port}"
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
    except (ValueError, UnicodeError):
        return None


def _normalise(rows: list[dict[str, Any]], limit: int) -> list[SearchResult]:
    results = []
    seen = set()
    for row in rows:
        url = _safe_url(row.get("href") or row.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        title = str(row.get("title") or "").strip()[:500]
        snippet = str(row.get("body") or row.get("snippet") or "").strip()[:2000]
        if not title and not snippet:
            continue
        results.append(SearchResult(len(results) + 1, title, url, snippet))
        if len(results) >= limit:
            break
    return results


def _score(query: str, results: list[SearchResult]) -> list[SearchResult]:
    terms = {w.casefold() for w in re.findall(r"[\w-]+", query) if len(w) > 2}
    if not terms:
        return results
    for item in results:
        title = {w.casefold() for w in re.findall(r"[\w-]+", item.title) if len(w) > 2}
        body = {w.casefold() for w in re.findall(r"[\w-]+", item.snippet) if len(w) > 2}
        item.score = round(0.65 * len(terms & title) / len(terms) +
                           0.35 * len(terms & body) / len(terms), 4)
    results.sort(key=lambda item: (-item.score, item.rank))
    for rank, item in enumerate(results, 1):
        item.rank = rank
    return results


def _cache_key(query: str, limit: int, region: str, safesearch: str) -> str:
    return hashlib.sha256(f"{query.casefold()}|{limit}|{region}|{safesearch}".encode()).hexdigest()


def _provider_search(query: str, limit: int, region: str, safesearch: str, timeout: float):
    from ddgs import DDGS
    return list(DDGS(timeout=max(1, int(timeout))).text(
        query, region=region, safesearch=safesearch, max_results=limit
    ) or [])


async def search(
    query: str,
    max_results: int = 5,
    *,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 2,
    cache_ttl: float = DEFAULT_CACHE_TTL,
    use_cache: bool = True,
    rerank: bool = True,
) -> list[SearchResult]:
    """Search the web and return normalized results."""
    query, limit = _validate_query(query, max_results)
    if safesearch not in {"on", "moderate", "off"}:
        raise SearchError("invalid_safesearch", "safesearch must be on, moderate, or off.")
    if not re.fullmatch(r"(wt-wt|[a-z]{2}-[a-z]{2})", region):
        raise SearchError("invalid_region", "Use a region such as 'us-en' or 'wt-wt'.")
    if timeout <= 0 or retries < 0 or retries > 5:
        raise SearchError("invalid_options", "timeout must be positive and retries must be 0-5.")

    key = _cache_key(query, limit, region, safesearch)
    if use_cache and cache_ttl > 0:
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
            if entry and time.monotonic() - entry[0] <= cache_ttl:
                _CACHE.move_to_end(key)
                cached = _normalise(entry[1], limit)
                return _score(query, cached) if rerank else cached
            if entry:
                del _CACHE[key]

    last_error = None
    for attempt in range(retries + 1):
        try:
            rows = await asyncio.wait_for(
                asyncio.to_thread(_provider_search, query, limit, region, safesearch, timeout),
                timeout=timeout + 2,
            )
            if use_cache and cache_ttl > 0:
                with _CACHE_LOCK:
                    _CACHE[key] = (time.monotonic(), rows)
                    _CACHE.move_to_end(key)
                    while len(_CACHE) > 256:
                        _CACHE.popitem(last=False)
            results = _normalise(rows, limit)
            return _score(query, results) if rerank else results
        except asyncio.TimeoutError as exc:
            last_error = exc
            code = "search_timeout"
        except ImportError as exc:
            raise SearchError("missing_dependency", "Install dependencies with: pip install -r requirements.txt") from exc
        except Exception as exc:
            last_error = exc
            code = "provider_unavailable"
        if attempt < retries:
            _LOG.warning("Search failed; retry %s/%s", attempt + 1, retries)
            await asyncio.sleep(min(3.0, 0.4 * 2**attempt) + random.uniform(0, 0.15))

    message = "Search provider timed out." if code == "search_timeout" else "Search provider is unavailable."
    raise SearchError(code, message) from last_error


def search_sync(query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(search(query, max_results, **kwargs))
    raise SearchError("event_loop_running", "Use 'await search(...)' inside an async function.")


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
