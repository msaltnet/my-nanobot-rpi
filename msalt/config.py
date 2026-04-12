from dataclasses import dataclass, field


@dataclass
class MsaltConfig:
    """msalt-nanobot 전용 설정."""
    timezone: str = "Asia/Seoul"
    news_sources_path: str = "msalt/news/sources.json"
    db_path: str = "msalt/data/msalt.db"
    briefing_morning: str = "07:00"
    briefing_evening: str = "19:00"
    collect_before_min: int = 30  # 브리핑 전 수집 시작 (분)
