"""msalt 뉴스 CLI — 스킬과 크론에서 호출하는 엔트리포인트."""
import sys

from msalt.config import MsaltConfig
from msalt.storage import Storage
from msalt.news.collector import NewsCollector
from msalt.news.briefing import BriefingGenerator


def _get_storage() -> Storage:
    config = MsaltConfig()
    storage = Storage(config.db_path)
    storage.initialize()
    return storage


def run_collect() -> str:
    storage = _get_storage()
    collector = NewsCollector(storage=storage)
    count = collector.collect()
    return f"뉴스 수집 완료: {count}건"


def run_briefing(time_of_day: str = "morning") -> str:
    storage = _get_storage()
    gen = BriefingGenerator(storage=storage)
    return gen.format_briefing(time_of_day)


def run_search(keyword: str) -> str:
    storage = _get_storage()
    articles = storage.get_articles_since("2020-01-01")
    matched = [a for a in articles if keyword.lower() in a["title"].lower()
               or keyword.lower() in a.get("summary", "").lower()]
    if not matched:
        return f"'{keyword}' 관련 뉴스를 찾을 수 없습니다."

    lines = [f"'{keyword}' 관련 뉴스 ({len(matched)}건)", ""]
    for i, a in enumerate(matched, 1):
        lines.append(f"{i}. [{a['source']}] {a['title']}")
        lines.append(f"   원문: {a['url']}")
        lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m msalt.news.cli [collect|briefing|search <keyword>]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "collect":
        print(run_collect())
    elif command == "briefing":
        time = sys.argv[2] if len(sys.argv) > 2 else "morning"
        print(run_briefing(time))
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python -m msalt.news.cli search <keyword>")
            sys.exit(1)
        print(run_search(sys.argv[2]))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
