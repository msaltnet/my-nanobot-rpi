import json
from datetime import datetime, timedelta

from msalt.lifestyle.classifier import classify_text
from msalt.storage import Storage


class LifeTracker:
    """자유 텍스트 생활 기록을 관리한다."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def log(self, text: str) -> int:
        result = classify_text(text)
        return self.storage.insert_life_log(
            raw_text=text,
            category=result["category"],
            parsed_data=json.dumps(result["parsed_data"], ensure_ascii=False),
        )

    def get_summary_by_category(self, days: int = 7) -> dict[str, int]:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return self.storage.get_life_log_category_counts(since)

    def format_summary(self, days: int = 7) -> str:
        summary = self.get_summary_by_category(days)
        if not summary:
            return f"최근 {days}일간 생활 기록이 없습니다."

        category_labels = {
            "exercise": "운동",
            "food": "식단",
            "health": "건강",
            "mood": "감정",
            "sleep": "수면",
            "other": "기타",
        }

        lines = [f"최근 {days}일 생활 기록 요약", ""]
        for cat, count in sorted(summary.items()):
            label = category_labels.get(cat, cat)
            lines.append(f"  {label}: {count}건")
        return "\n".join(lines)
