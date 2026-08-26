"""把 output/ 写成 TapTap Maker 工程。反编译出的资源在 assets/，玩法写在 scripts/。"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from gameaihack.agent.prompts.mission import INIT_CMD, INSTALL_CMD, output_agents, output_readme
from gameaihack.core.layout import output_dir  # noqa: F401


def emit_maker_project(job_dir: Path, ir: dict | None = None, *, run_init: bool | None = None) -> dict:
    """output/ 就是 Maker 工程：策划/、美术/，以及 init 出来的 scripts/、assets/、.project/。

    有 npx 时尝试在 output/ 执行 `npx -y @taptap/maker init`（已有工程则跳过）。
    不建 tests/。玩法由 agent 写进 scripts/，贴图在 assets/image/。
    """
    job_dir = Path(job_dir)
    dest = output_dir(job_dir)
    dest.mkdir(parents=True, exist_ok=True)
    _drop_tests(dest)
    ir = ir or {}
    pkg = ((ir.get("package") or {}).get("name") or job_dir.name).strip() or job_dir.name
    if run_init is None:
        run_init = (os.environ.get("GAMEAIHACK_MAKER_INIT") or "").strip() not in {"0", "off", "false"}
    inited = (dest / ".project" / "project.json").is_file() or (dest / "engine-docs").is_dir()
    init_ok = inited
    init_note = "已有 Maker 工程，跳过 init" if inited else ""
    if run_init and not inited:
        init_ok, init_note = _run_maker(["init"], dest, timeout=180)
    if run_init:
        _run_maker(["install", "--ide", "codex,cursor,claude"], dest, timeout=120)
    _link_maker_skill(dest)
    _drop_tests(dest)
    if init_ok:
        status = "已在本目录执行 `npx -y @taptap/maker init`。"
    elif not run_init and not inited:
        status = "Maker 目录骨架已写出。在本目录执行 `npx -y @taptap/maker init` 即可补齐引擎文件。"
    else:
        status = "Maker 目录骨架已写出，init 还没跑成。"
    extra = f"\n\n> {init_note}\n" if init_note and not init_ok else "\n"
    (dest / "README.md").write_text(output_readme(pkg, status=status, extra=extra), encoding="utf-8")
    (dest / "AGENTS.md").write_text(output_agents(pkg), encoding="utf-8")
    (dest / "scripts").mkdir(parents=True, exist_ok=True)
    for sub in ("image", "audio", "sprites"):
        (dest / "assets" / sub).mkdir(parents=True, exist_ok=True)
    return {
        "path": str(dest),
        "init": bool(init_ok),
        "note": init_note,
        "install": INSTALL_CMD,
        "init_cmd": INIT_CMD,
    }


def _drop_tests(dest: Path) -> None:
    tests = dest / "tests"
    if tests.exists():
        shutil.rmtree(tests, ignore_errors=True)


def _link_maker_skill(dest: Path) -> None:
    """把本机 taptap-maker skill 链进工程。"""
    home = Path.home() / ".agents" / "skills"
    src = None
    for name in ("taptap-maker--taptap-maker", "taptap-maker"):
        cand = home / name
        if cand.is_dir():
            src = cand
            break
    if src is None:
        return
    out = dest / ".claude" / "skills" / "taptap-maker"
    if out.exists() or out.is_symlink():
        return
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.symlink_to(src)
    except OSError:
        try:
            shutil.copytree(src, out)
        except OSError:
            pass


def _run_maker(args: list[str], cwd: Path, *, timeout: int) -> tuple[bool, str]:
    npx = shutil.which("npx")
    if not npx:
        return False, "没有 npx（需要 Node）。目录骨架已按 Maker 工程写出，可稍后在 output/ 执行 init。"
    cmd = [npx, "-y", "@taptap/maker", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "1", "npm_config_yes": "true"},
        )
    except subprocess.TimeoutExpired:
        return False, f"{' '.join(cmd)} 超时"
    except OSError as e:
        return False, str(e)
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return False, text[:800] or f"退出码 {proc.returncode}"
    return True, text[:400] or "ok"


class PackError(Exception):
    pass


_PACK_SKIP = {".apk", ".xapk", ".apks", ".obb", ".so", ".dll", ".exe", ".dylib"}


def pack_game(job_dir: Path, dest_zip: Path | None = None) -> dict:
    """把 output/ 这个 Maker 工程打成游戏包 zip。"""
    job = Path(job_dir).resolve()
    if job.name == "output":
        job_root, out = job.parent, job
    else:
        job_root, out = job, output_dir(job)
    if not out.is_dir():
        raise PackError(f"找不到 Maker 工程：{out}")
    dest = Path(dest_zip).resolve() if dest_zip else (job_root / f"{job_root.name}-game.zip")
    dest.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in out.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(out)
            parts = rel.parts
            if any(p in {"__pycache__", "tests"} for p in parts):
                continue
            if f.name in {".DS_Store"}:
                continue
            if f.suffix.lower() in _PACK_SKIP:
                continue
            rel = rel.as_posix()
            info = zipfile.ZipInfo(filename=rel)
            info.flag_bits |= 0x800
            info.date_time = time.localtime(f.stat().st_mtime)[:6]
            with f.open("rb") as src, zf.open(info, "w") as dst:
                shutil.copyfileobj(src, dst)
            added += 1
    if added == 0:
        raise PackError(f"工程是空的：{out}")
    return {
        "zip": str(dest),
        "added": added,
        "path": str(out),
    }
