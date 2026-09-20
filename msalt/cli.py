"""my-nanobot-rpi entry point.

사용자는 `my-nanobot-rpi`만 기억하면 된다. 이 커맨드는:

1. 프로젝트 루트의 `.env`를 환경 변수로 로드한다.
2. `~/.nanobot/config.json`과 `~/.nanobot/workspace/{SOUL,USER}.md`가
   없으면 msalt 기본 템플릿으로 seed한다.
3. 기본 동작은 nanobot gateway 기동.

서브커맨드:
  my-nanobot-rpi            (default) 게이트웨이 기동
  my-nanobot-rpi doctor     .env·config·RSS 연결 점검
  my-nanobot-rpi news ...   뉴스 수집/브리핑/검색
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
NANOBOT_HOME = Path.home() / ".nanobot"

SEED_CONFIG = HERE / "nanobot-config.example.json"
SEED_SOUL = HERE / "workspace" / "SOUL.md"
SEED_USER = HERE / "workspace" / "USER.md"
SEED_SKILLS_DIR = HERE / "skills"
SEED_CRON_JOBS = HERE / "workspace" / "cron" / "jobs.json"

REQUIRED_ENV_VARS = ("OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_USER_ID")


def _load_dotenv() -> Path | None:
    """프로젝트 루트와 CWD에서 .env를 찾아 로드. 발견된 경로 반환."""
    candidates = [REPO_ROOT / ".env", Path.cwd() / ".env"]
    for path in candidates:
        if path.is_file():
            try:
                from dotenv import load_dotenv
            except ImportError:
                # python-dotenv 없을 때 최소한의 자체 파서
                _load_env_file(path)
            else:
                load_dotenv(path, override=False)
            return path
    return None


def _load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _seed_if_missing() -> list[str]:
    """nanobot 설정/워크스페이스/스킬이 비어있으면 기본 템플릿 복사. 생성한 경로 리스트 반환."""
    created: list[str] = []
    NANOBOT_HOME.mkdir(parents=True, exist_ok=True)
    workspace_dir = NANOBOT_HOME / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    config_target = NANOBOT_HOME / "config.json"
    if not config_target.exists() and SEED_CONFIG.exists():
        shutil.copy2(SEED_CONFIG, config_target)
        created.append(str(config_target))

    for seed, target in [
        (SEED_SOUL, workspace_dir / "SOUL.md"),
        (SEED_USER, workspace_dir / "USER.md"),
    ]:
        if not target.exists() and seed.exists():
            shutil.copy2(seed, target)
            created.append(str(target))

    # msalt 스킬 → 워크스페이스 skills 디렉토리로 seed
    # nanobot SkillsLoader가 ~/.nanobot/workspace/skills/<name>/SKILL.md를 스캔한다.
    if SEED_SKILLS_DIR.exists():
        skills_target_root = workspace_dir / "skills"
        skills_target_root.mkdir(parents=True, exist_ok=True)
        for skill_dir in SEED_SKILLS_DIR.iterdir():
            if not skill_dir.is_dir():
                continue
            target = skills_target_root / skill_dir.name
            if _sync_seed_dir(skill_dir, target):
                created.append(str(target))

    # 크론 잡 seed — 아침/저녁 자동 브리핑.
    # jobs.json은 env var 치환을 지원하지 않아 seed 시점에 직접 ${TELEGRAM_USER_ID}를 박는다.
    cron_target = workspace_dir / "cron" / "jobs.json"
    if SEED_CRON_JOBS.exists() and _sync_seed_cron_jobs(cron_target):
        created.append(str(cron_target))
    return created


def _sync_seed_dir(seed_dir: Path, target_dir: Path) -> bool:
    """패키지에 포함된 관리 스킬을 workspace로 동기화한다.

    최초 seed 이후에도 SKILL.md의 실행 명령이 바뀔 수 있으므로, source에 있는 파일은
    target에 없거나 내용이 다를 때 덮어쓴다. 사용자가 target에 추가한 파일은 건드리지 않는다.
    """
    changed = False
    if not target_dir.exists():
        shutil.copytree(seed_dir, target_dir)
        return True

    for source in seed_dir.rglob("*"):
        rel = source.relative_to(seed_dir)
        target = target_dir / rel
        if source.is_dir():
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
                changed = True
            continue

        if not target.exists() or source.read_bytes() != target.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            changed = True

    return changed


def _sync_seed_cron_jobs(cron_target: Path) -> bool:
    """msalt가 관리하는 cron job을 최신 템플릿으로 갱신한다.

    기존 파일의 다른 job은 유지하고, msalt-news-* job은 최신 schedule/payload로 맞춘다.
    사용자가 job을 비활성화한 상태와 실행 state는 보존한다.
    """
    cron_target.parent.mkdir(parents=True, exist_ok=True)
    body = SEED_CRON_JOBS.read_text(encoding="utf-8")
    tg_id = os.environ.get("TELEGRAM_USER_ID", "").strip()
    if tg_id:
        body = body.replace("${TELEGRAM_USER_ID}", tg_id)
    seed_data = json.loads(body)

    if not cron_target.exists():
        cron_target.write_text(
            json.dumps(seed_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True

    try:
        existing_data = json.loads(cron_target.read_text(encoding="utf-8"))
    except Exception:
        backup = cron_target.with_suffix(cron_target.suffix + ".bak")
        shutil.copy2(cron_target, backup)
        cron_target.write_text(
            json.dumps(seed_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True

    seed_by_id = {job.get("id"): job for job in seed_data.get("jobs", []) if job.get("id")}
    existing_jobs = existing_data.get("jobs", [])
    rewritten_jobs = []
    seen_seed_ids = set()

    for existing in existing_jobs:
        job_id = existing.get("id")
        if job_id not in seed_by_id:
            rewritten_jobs.append(existing)
            continue

        updated = json.loads(json.dumps(seed_by_id[job_id], ensure_ascii=False))
        seen_seed_ids.add(job_id)

        for key in ("enabled", "state", "createdAtMs", "updatedAtMs", "deleteAfterRun"):
            if key in existing:
                updated[key] = existing[key]

        if not tg_id:
            existing_to = existing.get("payload", {}).get("to")
            if existing_to and existing_to != "${TELEGRAM_USER_ID}":
                updated.setdefault("payload", {})["to"] = existing_to

        rewritten_jobs.append(updated)

    for job_id, job in seed_by_id.items():
        if job_id not in seen_seed_ids:
            rewritten_jobs.append(job)

    updated_data = dict(existing_data)
    updated_data["version"] = seed_data.get("version", existing_data.get("version", 1))
    updated_data["jobs"] = rewritten_jobs

    old_text = json.dumps(existing_data, ensure_ascii=False, indent=2, sort_keys=True)
    new_text = json.dumps(updated_data, ensure_ascii=False, indent=2, sort_keys=True)
    if old_text == new_text:
        return False

    cron_target.write_text(
        json.dumps(updated_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def _check_env() -> list[str]:
    """필수 환경 변수가 비어있는지 검사. 누락된 변수 이름 리스트 반환."""
    missing = []
    for key in REQUIRED_ENV_VARS:
        val = os.environ.get(key, "").strip()
        if not val or val.startswith("your-") or val.endswith("-here"):
            missing.append(key)
    return missing


app = typer.Typer(
    name="my-nanobot-rpi",
    help="my-nanobot-rpi - 텔레그램 기반 개인 AI 비서 (nanobot 포크).",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
)


@app.callback()
def _default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        # 인자 없으면 gateway 기동
        gateway()


@app.command(help="게이트웨이 기동 (기본 동작).")
def gateway() -> None:
    env_path = _load_dotenv()
    created = _seed_if_missing()
    missing = _check_env()

    if env_path:
        console.print(f"[dim].env loaded: {env_path}[/dim]")
    else:
        console.print("[yellow]⚠ .env 파일을 찾지 못했습니다. .env.example을 복사해 채워주세요.[/yellow]")

    for path in created:
        console.print(f"[green]+ seed: {path}[/green]")

    if missing:
        console.print(f"[red]✗ 누락된 환경 변수: {', '.join(missing)}[/red]")
        console.print("[red]  .env를 편집한 뒤 다시 실행해주세요.[/red]")
        raise typer.Exit(code=1)

    # nanobot gateway로 인수 넘겨 기동
    from nanobot.cli.commands import app as nanobot_app
    sys.argv = ["nanobot", "gateway"]
    nanobot_app()


@app.command(help=".env · config · RSS 연결 상태 점검.")
def doctor() -> None:
    env_path = _load_dotenv()
    _seed_if_missing()

    console.print("[bold]my-nanobot-rpi doctor[/bold]\n")

    # 1. .env
    if env_path:
        console.print(f"[green]✓[/green] .env: {env_path}")
    else:
        console.print("[red]✗[/red] .env 파일 없음")

    # 2. 필수 환경 변수
    missing = _check_env()
    if not missing:
        console.print(f"[green]✓[/green] 환경 변수: {', '.join(REQUIRED_ENV_VARS)} OK")
    else:
        console.print(f"[red]✗[/red] 누락된 환경 변수: {', '.join(missing)}")

    # 3. 선택 키
    optional_present = [k for k in ("TAVILY_API_KEY", "BRAVE_API_KEY") if os.environ.get(k)]
    if optional_present:
        console.print(f"[green]✓[/green] 웹 검색 키: {', '.join(optional_present)}")
    else:
        console.print("[dim]- 웹 검색 키 없음 (DuckDuckGo fallback)[/dim]")

    # 4. config
    config_path = NANOBOT_HOME / "config.json"
    if config_path.exists():
        console.print(f"[green]✓[/green] config: {config_path}")
    else:
        console.print(f"[red]✗[/red] config 없음: {config_path}")

    # 5. 워크스페이스
    for name in ("SOUL.md", "USER.md"):
        p = NANOBOT_HOME / "workspace" / name
        mark = "[green]✓[/green]" if p.exists() else "[red]✗[/red]"
        console.print(f"{mark} workspace/{name}: {p}")

    # 6. 크론 잡 (아침/저녁 자동 브리핑)
    cron_path = NANOBOT_HOME / "workspace" / "cron" / "jobs.json"
    if cron_path.exists():
        import json as _json
        try:
            data = _json.loads(cron_path.read_text(encoding="utf-8"))
            enabled = [j for j in data.get("jobs", []) if j.get("enabled")]
            unresolved = [j["id"] for j in enabled
                          if "${TELEGRAM_USER_ID}" in _json.dumps(j)]
            if unresolved:
                console.print(f"[yellow]⚠[/yellow] cron: {len(enabled)}개 활성 (미치환 ${{TELEGRAM_USER_ID}}: {unresolved})")
            else:
                console.print(f"[green]✓[/green] cron: {len(enabled)}개 활성 ({cron_path})")
        except Exception as e:
            console.print(f"[red]✗[/red] cron 파싱 실패: {e}")
    else:
        console.print(f"[red]✗[/red] cron jobs.json 없음: {cron_path}")

    # 7. RSS 소스 점검
    console.print("\n[bold]뉴스 소스 점검[/bold]")
    from msalt.news.smoke import check_fallback, check_official, check_rss, check_search
    sources_path = str(HERE / "news" / "sources.json")
    rss_ok, rss_total = check_rss(sources_path)
    official_ok, official_total = check_official(sources_path)
    search_ok, search_total = check_search(sources_path)
    fallback_ok, fallback_total = check_fallback(sources_path)

    required_ok = (
        rss_ok == rss_total
        and official_ok == official_total
        and fallback_ok == fallback_total
        and rss_total > 0
    )
    search_ok_or_skipped = search_total == 0 or search_ok == search_total
    if required_ok and search_ok_or_skipped:
        console.print("\n[green]✓[/green] 뉴스 소스 정상")
    else:
        console.print("\n[yellow]⚠[/yellow] 일부 뉴스 소스 실패")

    if missing or not config_path.exists():
        raise typer.Exit(code=1)


news_app = typer.Typer(help="뉴스 수집·브리핑·검색.")
app.add_typer(news_app, name="news")


@news_app.command("collect", help="모든 RSS 소스에서 뉴스 수집.")
def news_collect() -> None:
    _load_dotenv()
    from msalt.news.cli import run_collect
    console.print(run_collect())


@news_app.command("briefing", help="아침/점심/저녁 브리핑 한 번 생성.")
def news_briefing(time_of_day: str = typer.Argument("morning", help="morning, afternoon 또는 evening")) -> None:
    _load_dotenv()
    from msalt.news.cli import run_briefing
    console.print(run_briefing(time_of_day))


@news_app.command("search", help="수집된 뉴스에서 키워드 검색.")
def news_search(keyword: str) -> None:
    _load_dotenv()
    from msalt.news.cli import run_search
    console.print(run_search(keyword))


@app.command(
    "tracking",
    help="추적 항목 add/list/delete/record/summary/dispatch.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def tracking(ctx: typer.Context) -> None:
    _load_dotenv()
    from msalt.tracking.cli import run_command
    raise typer.Exit(code=run_command(ctx.args))


if __name__ == "__main__":
    app()
