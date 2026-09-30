import json

from msalt.runtime_migration import maintain_runtime


def test_archives_activity_sections_and_keeps_profile(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    soul = "# SOUL\n\n## 성격\n한국어로 답한다.\n\n## 운영 노트\n- 2026-09-30: 브리핑 전송 완료\n"
    user = "# USER\n\n## 선호\n짧게 답한다.\n\n## 최근 기록\n- 2026-09-30: 수면 7시간\n"
    (workspace / "SOUL.md").write_text(soul, encoding="utf-8")
    (workspace / "USER.md").write_text(user, encoding="utf-8")
    (tmp_path / "config.json").write_text(
        json.dumps({"agents": {"defaults": {"contextWindowTokens": 16000}}}),
        encoding="utf-8",
    )

    maintain_runtime(tmp_path)

    assert "한국어로 답한다" in (workspace / "SOUL.md").read_text(encoding="utf-8")
    assert "수면 7시간" not in (workspace / "USER.md").read_text(encoding="utf-8")
    assert (workspace / "memory" / "profile-archive" / "SOUL.md").read_text(encoding="utf-8") == soul
    assert (workspace / "memory" / "profile-archive" / "USER.md").read_text(encoding="utf-8") == user
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["agents"]["defaults"]["contextWindowTokens"] == 64000
    before = (workspace / "SOUL.md").read_bytes()
    assert maintain_runtime(tmp_path) == []
    assert (workspace / "SOUL.md").read_bytes() == before


def test_preserves_custom_budget_and_non_activity_sections(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    user = "# USER\n\n## 최근 기록\n좋아하는 책은 Dune.\n"
    (workspace / "USER.md").write_text(user, encoding="utf-8")
    (tmp_path / "config.json").write_text(
        json.dumps({"agents": {"defaults": {"contextWindowTokens": 128000}}}),
        encoding="utf-8",
    )
    maintain_runtime(tmp_path)
    assert "Dune" in (workspace / "USER.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "config.json").read_text())["agents"]["defaults"]["contextWindowTokens"] == 128000
