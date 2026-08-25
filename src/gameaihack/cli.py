from __future__ import annotations

import json
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
from gameaihack.agent.dsh import DshError
from gameaihack.agent.drivers import AgentError
from gameaihack.ingest.fetch import FetchError, fetch_package, looks_like_package, resolve_proxy
from gameaihack.ingest import IngestError
from gameaihack.ingest.inspect import inspect_input
from gameaihack.content.ir import validate_ir
from gameaihack.publish.report import render_deliverable
from gameaihack.publish.share import ShareError, share_job

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="分析游戏包，把 output/ 写成 TapTap Maker 工程：策划 + 对照美术 + scripts/",
)

EXIT_USAGE = 2
EXIT_INGEST = 3
EXIT_SCHEMA = 4
EXIT_SHARE = 5
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


@app.command("inspect")
def inspect_cmd(
    input: Path = typer.Argument(..., exists=True, path_type=Path),
    obb: list[Path] = typer.Option(None, "--obb", help="额外 OBB，可重复"),
    hotupdate: Optional[Path] = typer.Option(None, "--hotupdate"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """指纹 + 输入完整度，几乎不写盘。"""
    try:
        result = inspect_input(input, obb or [], hotupdate)
    except IngestError as e:
        _die(str(e), EXIT_INGEST)
    if json_out:
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        typer.echo(result.to_text())


@app.command("fetch")
def fetch_cmd(
    package: str = typer.Argument(..., help="包名，如 com.unciv.app，或 Play 商店链接"),
    out: Path = typer.Option(Path("samples"), "--out", "-o", path_type=Path),
    source: str = typer.Option("auto", "--source", help="auto|fdroid|apkpure|gplaydl|evozi"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="下载代理（覆盖环境变量和 pipeline.yaml）"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="下载不走代理"),
    force_fetch: bool = typer.Option(False, "--force-fetch", help="忽略本地缓存，重新下载"),
) -> None:
    """按包名下载 APK。samples/ 里已有完整包则直接用。"""
    from gameaihack.ingest.fetch import find_cached, normalize_package

    if not force_fetch:
        try:
            cached = find_cached(normalize_package(package), out)
        except FetchError:
            cached = None
        if cached is None:
            typer.echo(f"下载代理：{resolve_proxy(proxy, disable=no_proxy) or '直连'}", err=True)
    else:
        typer.echo(f"下载代理：{resolve_proxy(proxy, disable=no_proxy) or '直连'}", err=True)
    try:
        result = fetch_package(
            package, out, source=source, proxy=proxy, no_proxy=no_proxy, force=force_fetch
        )
    except FetchError as e:
        _die(str(e), EXIT_INGEST)
    if result.source == "cache":
        typer.echo(f"使用缓存 {result.path}")
    typer.echo(f"{result.package}  ← {result.source}  {result.path}")
    if result.note:
        typer.echo(result.note)
    if result.extra_obbs:
        typer.echo("obb: " + ", ".join(str(p) for p in result.extra_obbs))


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
    """解开游戏包，抽出美术。Agent 读 raw/，把策划写到 output/。"""
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
    typer.echo(f"Maker 工程：{job_dir / 'output'}")
    typer.echo("  用 Cindy 打开上面这个目录。")
    typer.echo("  未装 MCP 时先：npx -y @taptap/maker install --ide codex,cursor,claude")
    typer.echo("  若还没有 .project：在该目录执行  npx -y @taptap/maker init")
    typer.echo(f"  策划：{job_dir / 'output' / '策划'}")
    typer.echo(f"  脚本：{job_dir / 'output' / 'scripts' / 'main.lua'}")
    typer.echo(f"  日志：{job_dir / 'run.log'}")
    typer.echo("发给别人：gameaihack share <该目录> --to ./结果.zip")


@app.command("maker")
def maker_cmd(job_dir: Path = typer.Argument(..., exists=True, path_type=Path)) -> None:
    """把已有 job 的 output/ 写成 TapTap Maker 工程（目录结构 + MCP 说明）。"""
    from gameaihack.core.layout import ir_dir
    from gameaihack.publish.maker import emit_maker_project

    ir_path = ir_dir(job_dir) / "game.ir.json"
    ir = {}
    if ir_path.is_file():
        try:
            ir = json.loads(ir_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            ir = {}
    mk = emit_maker_project(job_dir, ir if isinstance(ir, dict) else {})
    typer.echo(f"Maker 工程：{mk['path']}")
    typer.echo(f"  init：{'ok' if mk.get('init') else mk.get('note') or '骨架'}")
    typer.echo(f"  MCP：{mk.get('install')}")


@app.command("report")
def report_cmd(job_dir: Path = typer.Argument(..., exists=True, path_type=Path)) -> None:
    """按已有 IR 重出 HTML/封面。"""
    from gameaihack.core.layout import ir_dir

    ir_path = ir_dir(job_dir) / "game.ir.json"
    if not ir_path.exists():
        _die(f"找不到 {ir_path}", EXIT_USAGE)
    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    errs = validate_ir(ir)
    if errs:
        _die("IR 无效：\n" + "\n".join(errs), EXIT_SCHEMA)
    render_deliverable(job_dir, ir)
    from gameaihack.publish.kit import seal_kit

    seal_kit(job_dir, ir)
    typer.echo(f"复刻包：{job_dir / 'output'}")
    typer.echo(f"  说明：{job_dir / 'output' / '复刻说明.md'}")
    typer.echo(f"  日志：{job_dir / 'run.log'}")


@app.command("share")
def share_cmd(
    job_dir: Path = typer.Argument(..., exists=True, path_type=Path),
    to: Path = typer.Option(..., "--to", path_type=Path),
    strict: bool = typer.Option(False, "--strict-share"),
) -> None:
    """打可交接 zip（消毒，不含 apk/so）。"""
    try:
        info = share_job(job_dir, to, strict=strict)
    except ShareError as e:
        _die(str(e), EXIT_SHARE)
    typer.echo(f"已写入 {info['zip']}  （{info['added']} 文件，排除 {len(info['skipped'])}）")


@app.command("ir-validate")
def ir_validate_cmd(path: Path = typer.Argument(..., exists=True, path_type=Path)) -> None:
    ir = json.loads(path.read_text(encoding="utf-8"))
    errs = validate_ir(ir)
    if errs:
        typer.echo("\n".join(errs), err=True)
        raise typer.Exit(EXIT_SCHEMA)
    typer.echo("ok")
