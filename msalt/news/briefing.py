from datetime import datetime, timedelta

from msalt.storage import Storage


class BriefingGenerator:
    """수집된 뉴스를 브리핑 텍스트로 포맷한다."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def get_articles_for_briefing(self, hours: int = 12) -> list[dict]:
        since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        articles = self.storage.get_articles_since(since)
        # URL 기반 중복 제거
        seen_urls = set()
        unique = []
        for article in articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                unique.append(article)
        return unique

    def format_briefing(self, time_of_day: str = "morning") -> str:
        articles = self.get_articles_for_briefing()

        if not articles:
            label = "아침" if time_of_day == "morning" else "저녁"
            return f"{label} 경제 브리핑 — 수집된 뉴스가 없습니다."

        today = datetime.now().strftime("%Y-%m-%d")
        label = "아침" if time_of_day == "morning" else "저녁"

        domestic = [a for a in articles if a["category"] == "domestic"]
        international = [a for a in articles if a["category"] == "international"]
        policy = [a for a in articles if a["category"] == "policy"]
        reddit = [a for a in articles if a["category"] == "reddit"]

        lines = [f"{label} 경제 브리핑 ({today})", ""]

        if domestic:
            lines.append("[국내]")
            for i, a in enumerate(domestic, 1):
                lines.append(f"{i}. {a['title']}")
                if a.get("summary"):
                    lines.append(f"   {a['summary'][:200]}")
                lines.append(f"   원문: {a['url']}")
                lines.append("")

        if international:
            lines.append("[해외]")
            for i, a in enumerate(international, 1):
                lines.append(f"{i}. {a['title']}")
                if a.get("summary"):
                    lines.append(f"   {a['summary'][:200]}")
                lines.append(f"   원문: {a['url']}")
                lines.append("")

        if policy:
            lines.append("[정책·지표]")
            for i, a in enumerate(policy, 1):
                lines.append(f"{i}. [{a['source']}] {a['title']}")
                if a.get("summary"):
                    lines.append(f"   {a['summary'][:200]}")
                lines.append(f"   원문: {a['url']}")
                lines.append("")

        if reddit:
            lines.append("[커뮤니티]")
            for i, a in enumerate(reddit, 1):
                lines.append(f"{i}. [{a['source']}] {a['title']}")
                lines.append(f"   링크: {a['url']}")
                lines.append("")

        return "\n".join(lines)
