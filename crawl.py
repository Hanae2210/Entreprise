"""Crawl one or more URLs with crawl4ai and save each page as Markdown.

Usage:
    python crawl.py https://example.com [https://another.site ...] [-o output]
"""

import argparse
import asyncio
import re
from pathlib import Path
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig


def slugify(url: str) -> str:
    parsed = urlparse(url)
    slug = f"{parsed.netloc}{parsed.path}".strip("/") or parsed.netloc
    return re.sub(r"[^A-Za-z0-9._-]+", "_", slug)


async def crawl(urls: list[str], out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    failures = 0
    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun_many(urls=urls, config=run_config)
        for result in results:
            if not result.success:
                failures += 1
                print(f"FAILED  {result.url}: {result.error_message}")
                continue
            path = out_dir / f"{slugify(result.url)}.md"
            path.write_text(str(result.markdown), encoding="utf-8")
            print(f"OK      {result.url} -> {path}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("urls", nargs="+", help="URLs to crawl")
    parser.add_argument("-o", "--output", default="output", help="output directory")
    args = parser.parse_args()

    failures = asyncio.run(crawl(args.urls, Path(args.output)))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
