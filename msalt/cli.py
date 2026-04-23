"""msalt-nanobot entry point.

사용자는 `msalt-nanobot`만 기억하면 된다. 이 커맨드는:

1. 프로젝트 루트의 `.env`를 환경 변수로 로드한다.
2. `~/.nanobot/config.json`과 `~/.nanobot/workspace/{SOUL,USER}.md`가
   없으면 msalt 기본 템플릿으로 seed한다.
3. 기본 동작은 nanobot gateway 기동.

서브커맨드:
  msalt-nanobot            (default) 게이트웨이 기동
  msalt-nanobot doctor     .env·config·RSS 연결 점검
  msalt-nanobot news ...   뉴스 수집/브리핑/검색
"""
from __future__ import annotations

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
            if not target.exists():
                shutil.copytree(skill_dir, target)
                created.append(str(target))
    return created


def _check_env() -> list[str]:
    """필수 환경 변수가 비어있는지 검사. 누락된 변수 이름 리스트 반환."""
    missing = []
    for key in REQUIRED_ENV_VARS:
        val = os.environ.get(key, "").strip()
        if not val or val.startswith("your-") or val.endswith("-here"):
            missing.append(key)
    return missing


app = typer.Typer(
    name="msalt-nanobot",
    help="msalt-nanobot - 텔레그램 기반 개인 AI 비서 (nanobot 포크).",
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

    console.print("[bold]msalt-nanobot doctor[/bold]\n")

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

    # 6. RSS 소스 점검
    console.print("\n[bold]RSS 소스 점검[/bold]")
    from msalt.news.smoke import check_rss
    sources_path = str(HERE / "news" / "sources.json")
    ok, total = check_rss(sources_path)
    if ok == total and total > 0:
        console.print(f"\n[green]✓[/green] 모든 소스 정상 ({ok}/{total})")
    else:
        console.print(f"\n[yellow]⚠[/yellow] 일부 소스 실패 ({ok}/{total})")

    if missing or not config_path.exists():
        raise typer.Exit(code=1)


news_app = typer.Typer(help="뉴스 수집·브리핑·검색.")
app.add_typer(news_app, name="news")


@news_app.command("collect", help="모든 RSS 소스에서 뉴스 수집.")
def news_collect() -> None:
    _load_dotenv()
    from msalt.news.cli import run_collect
    console.print(run_collect())


@news_app.command("briefing", help="아침/저녁 브리핑 한 번 생성.")
def news_briefing(time_of_day: str = typer.Argument("morning", help="morning 또는 evening")) -> None:
    _load_dotenv()
    from msalt.news.cli import run_briefing
    console.print(run_briefing(time_of_day))


@news_app.command("search", help="수집된 뉴스에서 키워드 검색.")
def news_search(keyword: str) -> None:
    _load_dotenv()
    from msalt.news.cli import run_search
    console.print(run_search(keyword))


if __name__ == "__main__":
    app()
