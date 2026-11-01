from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import asdict, dataclass
from urllib.parse import urljoin, urlsplit

import aiohttp
from bs4 import BeautifulSoup

from .engine import SearchError, SearchResult, _safe_url, search

USER_AGENT = "KovoSearcher/1.0 (+https://github.com/kovo-searcher)"
MAX_PAGE_BYTES = 2_000_000
MAX_TEXT_CHARS = 30_000


@dataclass(slots=True)
class PageContent:
    url: str
    title: str
    text: str
    description: str = ""
    status: int = 200
    content_type: str = "text/html"

    def to_dict(self):
        return asdict(self)

    def to_rag_document(self):
        import hashlib
        return {
            "id": hashlib.sha256(self.url.encode()).hexdigest(),
            "text": self.text,
            "metadata": {
                "url": self.url,
                "title": self.title,
                "description": self.description,
                "source": "kovo_searcher",
            },
        }


async def _public_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            return False
        return bool(records) and all(ipaddress.ip_address(row[4][0]).is_global for row in records)


async def open_page(
    url: str,
    *,
    timeout: float = 15.0,
    max_chars: int = MAX_TEXT_CHARS,
    max_bytes: int = MAX_PAGE_BYTES,
) -> PageContent:
    """Fetch a public web page and extract its readable text."""
    current = _safe_url(url)
    if not current:
        raise SearchError("invalid_url", "Only valid public HTTP(S) URLs are supported.")

    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    async with aiohttp.ClientSession(timeout=timeout_cfg, headers=headers) as session:
        for _ in range(4):
            parts = urlsplit(current)
            if not await _public_host(parts.hostname or ""):
                raise SearchError("blocked_host", "The URL resolves to a non-public address.")
            async with session.get(current, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise SearchError("bad_redirect", "Redirect has no destination.")
                    current = _safe_url(urljoin(current, location))
                    if not current:
                        raise SearchError("blocked_redirect", "Redirect destination is not allowed.")
                    continue
                if response.status >= 400:
                    raise SearchError("http_error", f"Page returned HTTP {response.status}.")
                content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise SearchError("unsupported_content", "The URL did not return an HTML page.")
                length = response.content_length
                if length is not None and length > max_bytes:
                    raise SearchError("page_too_large", "Page exceeds the configured size limit.")
                body = await response.content.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise SearchError("page_too_large", "Page exceeds the configured size limit.")
                encoding = response.charset or "utf-8"
                html = body.decode(encoding, errors="replace")
                soup = BeautifulSoup(html, "lxml")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                meta = soup.find("meta", attrs={"name": "description"})
                description = meta.get("content", "").strip() if meta else ""
                for node in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
                    node.decompose()
                main = soup.find("main") or soup.find("article") or soup.body or soup
                text = " ".join(main.get_text(" ", strip=True).split())[:max_chars]
                return PageContent(
                    url=str(response.url), title=title[:500], text=text,
                    description=description[:1000], status=response.status,
                    content_type=content_type,
                )
        raise SearchError("too_many_redirects", "Page exceeded the redirect limit.")


def open_page_sync(url: str, **kwargs):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(open_page(url, **kwargs))
    raise SearchError("event_loop_running", "Use 'await open_page(...)' inside an async function.")


async def search_and_read(query: str, max_results: int = 5, *, read_limit: int = 3, **kwargs):
    """Search, then read the top results concurrently."""
    results = await search(query, max_results, **kwargs)
    pages = await asyncio.gather(
        *(open_page(item.url) for item in results[:max(0, min(read_limit, 5))]),
        return_exceptions=True,
    )
    return {
        "query": query,
        "results": [item.to_dict() for item in results],
        "pages": [
            page.to_dict() for page in pages if isinstance(page, PageContent)
        ],
        "page_errors": [
            {"error": str(page)} for page in pages if isinstance(page, Exception)
        ],
    }
