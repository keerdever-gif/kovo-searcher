from __future__ import annotations

import argparse
import asyncio
import json

from .browser import browse
from .engine import SearchError, search
from .reader import open_page, search_and_read


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kovo",
        description="Web search, page reading, and browser research tools for AI agents",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    find = sub.add_parser("search", help="Search the web with DuckDuckGo")
    find.add_argument("query")
    find.add_argument("-n", "--max-results", type=int, default=5)
    find.add_argument("--region", default="wt-wt")
    find.add_argument("--safesearch", choices=["on", "moderate", "off"], default="moderate")
    find.add_argument("--no-cache", action="store_true")

    read = sub.add_parser("open", help="Read a public HTML page")
    read.add_argument("url")

    research = sub.add_parser("research", help="Search and read top results without a browser")
    research.add_argument("query")
    research.add_argument("-n", "--max-results", type=int, default=5)

    browser = sub.add_parser("browse", help="Research a question with a Browser Use agent")
    browser.add_argument("query")
    browser.add_argument("--max-steps", type=int, default=8)
    browser.add_argument("--timeout", type=float, default=120.0)
    browser.add_argument("--model", help="Override the model configured in the environment")
    browser.add_argument("--cloud", action="store_true", help="Use Browser Use Cloud")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command == "search":
            data = asyncio.run(search(
                args.query,
                args.max_results,
                region=args.region,
                safesearch=args.safesearch,
                use_cache=not args.no_cache,
            ))
            payload = {"query": args.query, "results": [item.to_dict() for item in data]}
        elif args.command == "open":
            payload = asyncio.run(open_page(args.url)).to_dict()
        elif args.command == "research":
            payload = asyncio.run(search_and_read(args.query, args.max_results))
        else:
            payload = asyncio.run(browse(
                args.query,
                max_steps=args.max_steps,
                timeout=args.timeout,
                model=args.model,
                use_cloud=True if args.cloud else None,
            )).to_dict()

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except SearchError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
