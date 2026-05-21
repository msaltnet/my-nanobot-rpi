import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape


def clean_text(value: str | None) -> str:
    """HTML 조각과 공백을 사람이 읽을 수 있는 한 줄 텍스트로 정리."""
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_datetime(value: str | None) -> str | None:
    """여러 외부 API/HTML 날짜 문자열을 UTC 'YYYY-MM-DD HH:MM:SS'로 정규화."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    dt = None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        pass

    if dt is None:
        normalized = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if dt > datetime.now(timezone.utc):
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def current_utc_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
