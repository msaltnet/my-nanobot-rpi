from dataclasses import dataclass, field
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_DEFAULT_DB = str(Path.home() / ".nanobot" / "workspace" / "msalt.db")
_DEFAULT_SOURCES = str(_PKG_ROOT / "news" / "sources.json")


@dataclass
class MsaltConfig:
    """msalt-nanobot 전용 설정."""
    timezone: str = "Asia/Seoul"
    news_sources_path: str = _DEFAULT_SOURCES
    db_path: str = _DEFAULT_DB
    briefing_morning: str = "07:00"
    briefing_evening: str = "19:00"
    collect_before_min: int = 30  # 브리핑 전 수집 시작 (분)
