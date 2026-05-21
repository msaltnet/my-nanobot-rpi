"""실제 뉴스 소스 연결 진단 — 각 RSS 소스를 개별 호출해 OK/FAIL 리포트.

사용법:
    python -m msalt.news.smoke
"""
import argparse
import os
import sys
import time
import traceback

from msalt.config import MsaltConfig
from msalt.news.fallback import FallbackCollector
from msalt.news.official import OfficialFeedCollector
from msalt.news.rss import RssCollector
from msalt.news.search import SearchCollector


def _fmt_row(status: str, name: str, count: str, elapsed: str, detail: str) -> str:
    return f"  {status:<6} {name:<20} {count:>6}  {elapsed:>7}  {detail}"


def check_rss(sources_path: str) -> tuple[int, int]:
    collector = RssCollector(sources_path=sources_path)
    sources = collector.load_sources()
    if not sources:
        print("RSS: no sources found")
        return 0, 0

    print(f"\n=== RSS ({len(sources)} sources) ===")
    print(_fmt_row("STATUS", "NAME", "COUNT", "TIME(s)", "DETAIL"))
    ok = 0
    for src in sources:
        start = time.monotonic()
        try:
            articles = collector.collect_from_source(src)
            elapsed = time.monotonic() - start
            if articles:
                ok += 1
                sample = articles[0]["title"][:40]
                print(_fmt_row("OK", src["name"], str(len(articles)), f"{elapsed:.2f}", sample))
            else:
                print(_fmt_row("EMPTY", src["name"], "0", f"{elapsed:.2f}", "feed bozo or no entries"))
        except Exception as e:
            elapsed = time.monotonic() - start
            print(_fmt_row("FAIL", src["name"], "-", f"{elapsed:.2f}", f"{type(e).__name__}: {e}"))
    return ok, len(sources)


def check_official(sources_path: str) -> tuple[int, int]:
    collector = OfficialFeedCollector(sources_path=sources_path)
    sources = collector.load_sources()
    if not sources:
        print("\n=== Official feeds: no sources ===")
        return 0, 0

    print(f"\n=== Official feeds ({len(sources)} sources) ===")
    print(_fmt_row("STATUS", "NAME", "COUNT", "TIME(s)", "DETAIL"))
    ok = 0
    for src in sources:
        start = time.monotonic()
        articles = collector.rss.collect_from_source(src)
        elapsed = time.monotonic() - start
        if articles:
            ok += 1
            print(_fmt_row("OK", src["name"], str(len(articles)), f"{elapsed:.2f}", articles[0]["title"][:40]))
        else:
            print(_fmt_row("EMPTY", src["name"], "0", f"{elapsed:.2f}", "no entries"))
    return ok, len(sources)


def check_search(sources_path: str) -> tuple[int, int]:
    collector = SearchCollector(sources_path=sources_path)
    sources = collector.load_sources()
    if not sources:
        print("\n=== Search API: no sources ===")
        return 0, 0

    print(f"\n=== Search API ({len(sources)} sources) ===")
    print(_fmt_row("STATUS", "NAME", "COUNT", "TIME(s)", "DETAIL"))
    ok = 0
    checked = 0
    for src in sources:
        provider = src.get("provider", "")
        env_name = src.get("api_key_env") or (
            "TAVILY_API_KEY" if provider == "tavily" else "BRAVE_API_KEY"
        )
        if not os.environ.get(env_name, "").strip():
            print(_fmt_row("SKIP", src["name"], "-", "-", f"{env_name} missing"))
            continue
        checked += 1
        start = time.monotonic()
        if provider == "tavily":
            articles = collector._collect_tavily(src)
        elif provider == "brave":
            articles = collector._collect_brave(src)
        else:
            articles = []
        elapsed = time.monotonic() - start
        if articles:
            ok += 1
            print(_fmt_row("OK", src["name"], str(len(articles)), f"{elapsed:.2f}", articles[0]["title"][:40]))
        else:
            print(_fmt_row("EMPTY", src["name"], "0", f"{elapsed:.2f}", "no results"))
    return ok, checked


def check_fallback(sources_path: str) -> tuple[int, int]:
    collector = FallbackCollector(sources_path=sources_path)
    sources = collector.load_sources()
    if not sources:
        print("\n=== Fallback: no sources ===")
        return 0, 0

    print(f"\n=== Fallback ({len(sources)} sources) ===")
    print(_fmt_row("STATUS", "NAME", "COUNT", "TIME(s)", "DETAIL"))
    ok = 0
    for src in sources:
        start = time.monotonic()
        articles = []
        if src.get("sitemap_url"):
            articles.extend(collector.collect_from_sitemap(src))
        if src.get("url"):
            articles.extend(collector.collect_from_html(src))
        elapsed = time.monotonic() - start
        if articles:
            ok += 1
            print(_fmt_row("OK", src["name"], str(len(articles)), f"{elapsed:.2f}", articles[0]["title"][:40]))
        else:
            print(_fmt_row("EMPTY", src["name"], "0", f"{elapsed:.2f}", "no links"))
    return ok, len(sources)


def main() -> int:
    parser = argparse.ArgumentParser(description="msalt news source smoke test")
    parser.add_argument("--sources", default=MsaltConfig().news_sources_path)
    parser.add_argument("--verbose", action="store_true", help="print full tracebacks on failure")
    args = parser.parse_args()

    try:
        rss_ok, rss_total = check_rss(args.sources)
        official_ok, official_total = check_official(args.sources)
        search_ok, search_total = check_search(args.sources)
        fallback_ok, fallback_total = check_fallback(args.sources)
    except Exception:
        if args.verbose:
            traceback.print_exc()
        raise

    print("\n=== Summary ===")
    print(f"  RSS : {rss_ok}/{rss_total} OK")
    print(f"  Official : {official_ok}/{official_total} OK")
    print(f"  Search : {search_ok}/{search_total} OK")
    print(f"  Fallback : {fallback_ok}/{fallback_total} OK")

    required_ok = (
        rss_ok == rss_total
        and official_ok == official_total
        and fallback_ok == fallback_total
        and rss_total > 0
    )
    search_ok_or_skipped = search_total == 0 or search_ok == search_total
    return 0 if required_ok and search_ok_or_skipped else 1


if __name__ == "__main__":
    sys.exit(main())
