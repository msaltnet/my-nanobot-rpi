from pathlib import Path

from msalt.config import MsaltConfig


def test_default_config():
    config = MsaltConfig()
    assert config.timezone == "Asia/Seoul"
    assert config.briefing_morning == "07:00"
    assert config.briefing_evening == "19:00"


def test_default_db_path_is_in_nanobot_home():
    config = MsaltConfig()
    expected = Path.home() / ".nanobot" / "workspace" / "msalt.db"
    assert config.db_path == str(expected)


def test_default_sources_path_is_absolute_and_exists():
    config = MsaltConfig()
    p = Path(config.news_sources_path)
    assert p.is_absolute()
    assert p.exists()
    assert p.name == "sources.json"


def test_custom_config():
    config = MsaltConfig(timezone="UTC", briefing_morning="08:00")
    assert config.timezone == "UTC"
    assert config.briefing_morning == "08:00"
