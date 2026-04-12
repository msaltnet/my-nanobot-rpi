from msalt.config import MsaltConfig


def test_default_config():
    config = MsaltConfig()
    assert config.timezone == "Asia/Seoul"
    assert config.news_sources_path == "msalt/news/sources.json"
    assert config.db_path == "msalt/data/msalt.db"
    assert config.briefing_morning == "07:00"
    assert config.briefing_evening == "19:00"


def test_custom_config():
    config = MsaltConfig(timezone="UTC", briefing_morning="08:00")
    assert config.timezone == "UTC"
    assert config.briefing_morning == "08:00"
