from datetime import datetime, timedelta

from msalt.storage import Storage


class SleepTracker:
    """수면 기록을 관리한다."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def record(self, date: str, bedtime: str, wakeup: str,
               duration_min: int, quality: str | None = None):
        self.storage.upsert_sleep(date, bedtime, wakeup, duration_min, quality)

    def get_stats(self, days: int = 7) -> dict:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        logs = self.storage.get_sleep_logs_since(since)
        if not logs:
            return {"count": 0, "avg_duration_min": 0, "min_duration_min": 0, "max_duration_min": 0}

        durations = [log["duration_min"] for log in logs]
        return {
            "count": len(logs),
            "avg_duration_min": round(sum(durations) / len(durations)),
            "min_duration_min": min(durations),
            "max_duration_min": max(durations),
        }

    def format_stats(self, days: int = 7) -> str:
        stats = self.get_stats(days)
        if stats["count"] == 0:
            return f"최근 {days}일간 수면 기록이 없습니다."

        return (
            f"최근 {days}일 수면 통계 ({stats['count']}건)\n"
            f"  평균: {stats['avg_duration_min']}분 ({stats['avg_duration_min'] // 60}시간 {stats['avg_duration_min'] % 60}분)\n"
            f"  최소: {stats['min_duration_min']}분\n"
            f"  최대: {stats['max_duration_min']}분"
        )
