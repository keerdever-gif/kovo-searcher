# Kovo Searcher
<div align="center">
  <img src="Imagenes/kovo.gif" width="100%" alt="Kovo-Searcher Banner">
  
  <br>
  <br>

  <a href="https://github.com/keerdever-gif/kovo-searcher/releases"><img src="https://img.shields.io/badge/version-0.2.0-blue?style=for-the-badge" alt="Version"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-yellow?style=for-the-badge" alt="Python"></a>
  <a href="https://github.com/keerdever-gif/kovo-searcher/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/status-active-brightgreen?style=for-the-badge" alt="Status">
</div>

<br>
## Features

- DuckDuckGo search with normalized results, relevance scoring, retries, and an in-memory cache.
- Safe HTML page reading with redirect checks, response limits, and readable-text extraction.
- `search_and_read()` for fast, low-cost research without launching a browser.
- `browse()` for agent-driven navigation through dynamic pages with Browser Use.
- Local browser support, with optional Browser Use Cloud support.
- Async-first API, synchronous helpers, JSON CLI output, and RAG-friendly documents.
- Browser Use is an optional dependency; the original search tools stay lightweight.

## Requirements

- Python 3.10+ for core search and page reading.
- Python 3.11+ for the optional Browser Use integration.

## Installation

Create and activate a virtual environment:

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
```

Install the core package:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

To install the test tools:

```bash
python -m pip install -r requirements-dev.txt
```

To enable Browser Use (Python 3.11+):

```bash
python -m pip install -r requirements-browser.txt
playwright install chromium
```

Or install the package extra:

```bash
python -m pip install '.[browser]'
playwright install chromium
```

## Quick start: lightweight search

This mode does not require an LLM API key or a browser.

```python
import asyncio
from kovo_searcher import search, open_page, search_and_read

async def main():
    results = await search("Python asyncio task groups", max_results=5)
    for item in results:
        print(item.title, item.url)

    if results:
        page = await open_page(results[0].url)
        print(page.title)
        print(page.text[:1000])

    research = await search_and_read("Python packaging best practices", read_limit=3)
    print(research["pages"])

asyncio.run(main())
```

## Browser Use: dynamic web research

The Browser Use mode starts an agent that can search and navigate pages in a real browser. It is useful for sites that need JavaScript or multi-step navigation.

### Configure a model

Copy `.env.example` to `.env` and add your API key. Browser mode loads `.env` automatically when `python-dotenv` is installed (included in the Browser Use requirements). Existing environment variables take precedence over values in `.env`.

The recommended Browser Use model provider uses `BROWSER_USE_API_KEY`:

```bash
# macOS / Linux
export BROWSER_USE_API_KEY="your-key"

# Windows PowerShell
# $env:BROWSER_USE_API_KEY="your-key"
```

You can also use an OpenAI model directly:

```bash
export KOVO_MODEL_PROVIDER=openai
export OPENAI_API_KEY="your-key"
```

With `KOVO_MODEL_PROVIDER=auto` (the default), Kovo prefers Browser Use when `BROWSER_USE_API_KEY` is set, otherwise it uses OpenAI when `OPENAI_API_KEY` is set.

### Python API

```python
import asyncio
from kovo_searcher import browse

async def main():
    result = await browse(
        "Compare the official documentation for FastAPI and Flask",
        max_steps=8,
        timeout=120,
    )
    print(result.answer)
    print(result.sources)

asyncio.run(main())
```

Synchronous scripts can use `browse_sync()`:

```python
from kovo_searcher import browse_sync

result = browse_sync("Find the official Python documentation for asyncio")
print(result.to_dict())
```

### Local browser or cloud browser

Local browser is the default. Browser Use Cloud is optional and requires `BROWSER_USE_API_KEY`:

```python
result = await browse("Research this topic", use_cloud=True)
```

You can also set `KOVO_BROWSER_CLOUD=true` to enable cloud mode by default. Cloud browser usage may incur separate service charges; check the provider's current pricing before enabling it.

## Agent tool pattern

Expose Kovo functions as tools in your agent framework:

```python
from kovo_searcher import browse, open_page, search

async def web_search_tool(query: str) -> dict:
    results = await search(query, max_results=6)
    return {"results": [item.to_dict() for item in results]}

async def read_webpage_tool(url: str) -> dict:
    return (await open_page(url)).to_dict()

async def browser_research_tool(query: str) -> dict:
    return (await browse(query, max_steps=8)).to_dict()
```

Use `search` and `open_page` for quick, predictable retrieval. Use `browse` when a real browser is needed. `BrowserResearchResult.to_rag_document()` and the existing result classes provide RAG-friendly output.

## CLI

```bash
# Search results only
kovo search "AI agent tool calling" --max-results 5

# Read a public HTML page
kovo open "https://example.com"

# Search, then read the top pages without a browser
kovo research "Python web automation libraries" --max-results 5

# Use Browser Use for dynamic browser research
kovo browse "Compare the official docs for Playwright and Selenium" --max-steps 8

# Use Browser Use Cloud
kovo browse "Research this topic" --cloud
```

All commands print JSON to stdout. They can also be run without installing the console script:

```bash
python -m kovo_searcher.cli browse "Research Python asyncio"
```

## Result formats

Search results expose:

```json
{
  "rank": 1,
  "title": "Example",
  "url": "https://example.com/",
  "snippet": "A short search result summary.",
  "score": 0.42,
  "source": "duckduckgo"
}
```

Browser research returns:

```json
{
  "query": "Research question",
  "answer": "A concise answer with Markdown source links.",
  "sources": [
    {"title": "Example", "url": "https://example.com/"}
  ],
  "model": "bu-2-0",
  "provider": "browser-use"
}
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `KOVO_MODEL_PROVIDER` | `auto` | `auto`, `browser-use`, or `openai` |
| `BROWSER_USE_API_KEY` | — | Browser Use model or cloud-browser access |
| `KOVO_BROWSER_MODEL` | `bu-2-0` | Model used with Browser Use |
| `OPENAI_API_KEY` | — | Direct OpenAI model access |
| `KOVO_OPENAI_MODEL` | `gpt-4o-mini` | Model used with OpenAI |
| `KOVO_BROWSER_CLOUD` | `false` | Use Browser Use Cloud by default |

Browser Use mode also accepts `model`, `max_steps`, `timeout`, and `use_cloud` as Python arguments. `max_steps` is limited to 1–30 and the timeout to 600 seconds.

## Security and limitations

- The regular page reader accepts only public HTTP(S) pages, checks redirect destinations, and caps response sizes.
- Browser mode is intended for public, read-only research. Its task prompt tells the agent not to sign in, submit forms, download files, or make changes. This is an agent instruction, not a hard sandbox over every browser action.
- Use a separate browser profile without personal accounts for agent research. Do not point agents at private dashboards or pages containing secrets.
- Page content is untrusted input and may contain prompt-injection attempts. Kovo's browser task explicitly tells the agent to ignore instructions found in web pages.
- Browser Use Cloud is a separate hosted service; its use may have separate costs and data-handling terms.
- The core HTTP reader does not execute JavaScript. Use Browser Use for sites that require dynamic rendering.

## Project layout

```text
Kovo-Searcher/
├── kovo_searcher/
│   ├── __init__.py
│   ├── browser.py
│   ├── cli.py
│   ├── engine.py
│   └── reader.py
├── tests/
│   ├── test_browser.py
│   ├── test_engine.py
│   └── test_reader.py
├── .env.example
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── requirements-browser.txt
└── README.md
```

## Tests

```bash
pytest -q
python -m compileall -q kovo_searcher tests
```

The test suite mocks search providers, HTTP responses, and Browser Use agents. It does not launch a browser or make paid LLM requests.

## License

No license file is included yet. Add the license you intend to publish under before distributing the project.
