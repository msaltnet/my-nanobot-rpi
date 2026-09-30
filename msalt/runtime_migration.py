"""Keep legacy activity journals out of the always-loaded agent profiles."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PROFILE_POLICY = """## 메모리 저장 원칙

- SOUL.md와 USER.md에는 성격, 선호, 지속적인 설정만 보관한다. 각 파일을 6,000자 이내로 유지한다.
- 브리핑 전송 내역, 일별 생활 기록, 실행 오류, 날짜별 통계는 프로필에 누적하지 않는다.
- 생활 기록과 통계는 msalt.db가 기준이며, 과거 실행 내역은 memory/history.jsonl에서 찾아본다.
- memory/profile-archive/는 이전 프로필 원본의 보관 장소다. 내용을 프로필로 다시 복사하지 않는다.
"""


def _backup(path: Path, destination: Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_text(encoding="utf-8") == content:
            return
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        destination = destination.with_name(f"{path.stem}-{digest}{path.suffix}")
    if not destination.exists():
        destination.write_text(content, encoding="utf-8")


def _write(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".migration.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def maintain_runtime(nanobot_home: Path) -> list[str]:
    """Archive known legacy journal sections, preserving original files and custom budgets."""
    changed: list[str] = []
    workspace = nanobot_home / "workspace"
    for name, heading in [("SOUL.md", "운영 노트"), ("USER.md", "최근 기록")]:
        path = workspace / name
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        pattern = re.compile(rf"^## {heading}\s*\n.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)

        def remove_journal(match: re.Match[str]) -> str:
            return "" if re.search(r"\d{4}-\d{2}-\d{2}", match.group()) else match.group()

        cleaned = pattern.sub(remove_journal, original)
        if name == "SOUL.md" and "## 메모리 저장 원칙" not in cleaned:
            cleaned = cleaned.rstrip() + "\n\n" + PROFILE_POLICY
        if cleaned != original:
            _backup(path, workspace / "memory" / "profile-archive" / name, original)
            _write(path, cleaned)
            changed.append(str(path))

    config_path = nanobot_home / "config.json"
    if config_path.exists():
        original = config_path.read_text(encoding="utf-8")
        config = json.loads(original)
        defaults = config.get("agents", {}).get("defaults", {})
        budget_key = "contextWindowTokens" if "contextWindowTokens" in defaults else "context_window_tokens"
        if defaults.get(budget_key) == 16000:
            defaults[budget_key] = 64000
            _backup(config_path, nanobot_home / "config-backups" / "config.json", original)
            _write(config_path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
            changed.append(str(config_path))
    return changed
