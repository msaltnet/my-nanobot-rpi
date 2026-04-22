"""실제 뉴스 소스 연결 진단 — 각 RSS 소스를 개별 호출해 OK/FAIL 리포트.

사용법:
    python -m msalt.news.smoke
"""
import argparse
import sys
import time
import traceback

from msalt.config import MsaltConfig
from msalt.news.rss import RssCollector


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


def main() -> int:
    parser = argparse.ArgumentParser(description="msalt news source smoke test")
    parser.add_argument("--sources", default=MsaltConfig().news_sources_path)
    parser.add_argument("--verbose", action="store_true", help="print full tracebacks on failure")
    args = parser.parse_args()

    try:
        rss_ok, rss_total = check_rss(args.sources)
    except Exception:
        if args.verbose:
            traceback.print_exc()
        raise

    print("\n=== Summary ===")
    print(f"  RSS : {rss_ok}/{rss_total} OK")

    return 0 if rss_ok == rss_total and rss_total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
