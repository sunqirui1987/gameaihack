from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

try:
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

import typer

from gameaihack import __version__
from gameaihack.pipeline.run import analyze
from gameaihack.doctor import run_doctor
from gameaihack.agent.drivers import AgentError
from gameaihack.agent.drivers.dsh import DshError
from gameaihack.ingest.fetch import FetchError, fetch_package, looks_like_package, resolve_proxy
from gameaihack.ingest import IngestError

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="提取策划与美术，用 TapTap Maker 做成玩法一模一样的新游戏",
)

EXIT_USAGE = 2
EXIT_INGEST = 3
EXIT_SCHEMA = 4
EXIT_BUILD = 5
EXIT_DOCTOR = 10


def _die(msg: str, code: int) -> None:
    typer.echo(msg, err=True)
    raise typer.Exit(code)


@app.command()
def doctor() -> None:
    """检查运行环境。"""
    checks, required_fail = run_doctor()
    for c in checks:
        flag = "OK " if c.ok else "MISS"
        req = "required" if c.required else "optional"
        typer.echo(f"[{flag}] {c.name:16} ({req}) {c.detail}")
    typer.echo(f"gameaihack {__version__}")
    if required_fail:
        raise typer.Exit(EXIT_DOCTOR)


@app.command("analyze")
def analyze_cmd(
    target: str = typer.Argument(..., help="apk/xapk 路径，或包名 / Play 链接"),
    mode: str = typer.Option("standard", "--mode"),
    out: Path = typer.Option(Path("jobs"), "--out", path_type=Path),
    obb: list[Path] = typer.Option(None, "--obb"),
    hotupdate: Optional[Path] = typer.Option(None, "--hotupdate"),
    device: Optional[str] = typer.Option(None, "--device"),
    i_have_rights: bool = typer.Option(False, "--i-have-rights"),
    thumbs_only: bool = typer.Option(True, "--thumbs-only/--full-assets"),
    job_id: Optional[str] = typer.Option(None, "--job-id"),
    from_stage: Optional[str] = typer.Option(None, "--from-stage"),
    resume: bool = typer.Option(False, "--resume"),
    config: Optional[Path] = typer.Option(None, "--config", path_type=Path),
    source: str = typer.Option("auto", "--source", help="auto|fdroid|apkpure|gplaydl|evozi"),
    fetch_dir: Path = typer.Option(Path("samples"), "--fetch-dir", path_type=Path),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="下载代理（覆盖环境变量和 pipeline.yaml）"),
    no_proxy: bool = typer.Option(False, "--no-proxy"),
    force_fetch: bool = typer.Option(False, "--force-fetch", help="忽略本地缓存，重新下载"),
    via: Optional[str] = typer.Option(
        None,
        "--via",
        help="sdk（默认，DSH Python harness）| grok | codex | dsh（本机 CLI）",
    ),
) -> None:
    """解包 → 提取美术/策划 → 用 Maker 做成同一套游戏。"""
    if mode not in {"brief", "standard", "deep"}:
        _die("--mode 必须是 brief|standard|deep", EXIT_USAGE)
    if from_stage and from_stage not in {
        "unpack",
        "fingerprint",
        "extract",
        "normalize",
        "levels",
        "design",
        "ai",
        "report",
    }:
        _die("--from-stage 非法", EXIT_USAGE)
    if (from_stage or resume) and not job_id:
        _die("--resume / --from-stage 必须同时给 --job-id", EXIT_USAGE)
    if config:
        import os

        cfg = config.resolve()
        os.environ["GAMEAIHACK_CONFIGS"] = str(cfg.parent if cfg.is_file() else cfg)
    if not i_have_rights:
        if not sys.stdin.isatty():
            _die("非交互环境必须加 --i-have-rights 以确认有权分析该包。", EXIT_USAGE)
        ok = typer.confirm("确认有权分析这个包？", default=False)
        if not ok:
            _die("已取消。", EXIT_USAGE)
    input_path = Path(target)
    extra_obb = list(obb or [])
    if not input_path.exists():
        if not looks_like_package(target):
            _die(f"找不到文件，也不是包名：{target}", EXIT_USAGE)
        from gameaihack.ingest.fetch import find_cached, normalize_package

        try:
            cached = None if force_fetch else find_cached(normalize_package(target), fetch_dir)
        except FetchError:
            cached = None
        if cached is None:
            typer.echo(f"下载代理：{resolve_proxy(proxy, disable=no_proxy) or '直连'}", err=True)
        try:
            result = fetch_package(
                target, fetch_dir, source=source, proxy=proxy, no_proxy=no_proxy, force=force_fetch
            )
        except FetchError as e:
            _die(str(e), EXIT_INGEST)
        input_path = result.path
        extra_obb.extend(result.extra_obbs)
        if result.source == "cache":
            typer.echo(f"使用缓存 {result.path}")
        else:
            typer.echo(f"已下载 [{result.source}] {result.path}  {result.note}")
    try:
        job_dir = analyze(
            input_path,
            out=out,
            mode=mode,
            obb=extra_obb,
            hotupdate=hotupdate,
            job_id=job_id,
            argv=sys.argv,
            thumbs_only=thumbs_only,
            device=device,
            from_stage=from_stage,
            resume=resume,
            via=via,
        )
    except IngestError as e:
        _die(str(e), EXIT_INGEST)
    except (AgentError, DshError) as e:
        _die(str(e), EXIT_DOCTOR)
    except ValueError as e:
        _die(str(e), EXIT_SCHEMA)
    typer.echo(f"1 美术：{job_dir / 'output' / 'assets'}")
    typer.echo(f"2 策划 PRD：{job_dir / 'output' / '策划' / '02-核心玩法.md'}")
    typer.echo(f"3 新游戏：{job_dir / 'output'}")
    typer.echo(f"打包：gameaihack build {job_dir}")
    typer.echo(f"日志：{job_dir / 'run.log'}")


@app.command("build")
def build_cmd(
    job_dir: Path = typer.Argument(..., exists=True, path_type=Path),
    to: Optional[Path] = typer.Option(None, "--to", help="输出 zip 路径"),
) -> None:
    """打包 output/ 里的 Maker 游戏。"""
    from gameaihack.publish.maker import PackError, pack_game

    try:
        info = pack_game(job_dir, to)
    except PackError as e:
        _die(str(e), EXIT_BUILD)
    typer.echo(f"游戏包：{info['zip']}  （{info['added']} 个文件）")
    typer.echo(f"工程：{info['path']}")
