"""解包之后跑一遍 agent：提示词来自 prompts，通道来自 drivers。"""

from __future__ import annotations

import os
import time
from pathlib import Path

from gameaihack.agent.corpus import index_markdown, iter_source_files
from gameaihack.agent.drivers import AgentRequest, is_retryable, parse_via, resolve_driver
from gameaihack.agent.llm import LlmConfig, resolve_llm
from gameaihack.agent.prompts import drive_tasks, gap_prompt, write_workspace_agents
from gameaihack.core.layout import design_dir


def _retry_delays() -> list[float]:
    raw = os.environ.get("GAMEAIHACK_LLM_RETRY", "15,30,60")
    text = (raw or "").strip().lower()
    if text in {"0", "off", "none", ""}:
        return []
    out: list[float] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(max(0.0, float(part)))
        except ValueError:
            continue
    return out


def _run_driver(driver, req: AgentRequest, *, cfg=None) -> dict:
    delays = _retry_delays()
    last: dict = {"ok": False, "via": getattr(driver, "via", ""), "error": "未知错误"}
    attempts = 1 + len(delays)
    from gameaihack.core.progress import log

    for i in range(attempts):
        last = driver.run(req, cfg=cfg)
        if last.get("ok"):
            return last
        err = str(last.get("error") or "")
        if i >= attempts - 1 or not is_retryable(err):
            return last
        wait = delays[i]
        log(f"[{driver.via}] 并发/限额，{int(wait)}s 后重试（{i + 1}/{attempts}）：{err[:160]}")
        if wait:
            time.sleep(wait)
    return last


def run_book(
    job_dir: Path,
    ir: dict,
    cfg: LlmConfig | None,
    *,
    via: str = "sdk",
    tasks: list[tuple[str, str]] | None = None,
    workspace: Path | None = None,
) -> dict:
    from gameaihack.core.progress import log, stream

    via = parse_via(via)
    driver = resolve_driver(via)
    driver.require(cfg)
    dest = design_dir(job_dir)
    dest.mkdir(parents=True, exist_ok=True)
    stale = dest / "过程.md"
    if stale.is_file():
        try:
            stale.unlink()
        except OSError:
            pass
    tasks = list(tasks) if tasks is not None else drive_tasks(job_dir, ir)
    results: list[dict] = []
    all_ok = True
    effort = (os.environ.get("GAMEAIHACK_EFFORT") or "xhigh").strip() or "xhigh"
    try:
        for i, (title, prompt) in enumerate(tasks, 1):
            stream(f"\n{via}  {i}/{len(tasks)}  {title}")
            req = AgentRequest(
                job_dir=job_dir,
                prompt=prompt,
                model=(cfg.model if cfg else "") or os.environ.get("LLM_MODELS") or "grok-4.6",
                timeout=int(os.environ.get("GAMEAIHACK_AGENT_TIMEOUT") or "3600"),
                effort=effort,
                api_key=cfg.api_key if cfg else "",
                base_url=cfg.base_url if cfg else "",
                cwd=workspace,
            )
            step = _run_driver(driver, req, cfg=cfg)
            results.append({"title": title, "ok": step.get("ok"), "error": step.get("error")})
            if step.get("ok"):
                stream(f"{via}  {title}  done")
            else:
                all_ok = False
                log(f"[{via}] 失败：{step.get('error') or 'unknown'}")
                break
    finally:
        closer = getattr(driver, "close", None)
        if callable(closer):
            closer()
    err = next((r.get("error") for r in results if not r.get("ok")), "")
    return {"ok": all_ok, "via": via, "error": err or "", "steps": results}


def run_ai_analysis(
    job_dir: Path,
    ir: dict,
    *,
    cfg: LlmConfig | None = None,
    via: str = "sdk",
) -> dict:
    """提取策划 PRD，并按它在 Maker 里做成同一套游戏。"""
    if cfg is None:
        cfg = resolve_llm()
    dest = design_dir(job_dir) / "ai"
    dest.mkdir(parents=True, exist_ok=True)
    files = iter_source_files(job_dir)
    (dest / "文件索引.md").write_text(index_markdown(job_dir, files), encoding="utf-8")
    result: dict = {
        "files": len(files),
        "via": via,
        "dsh": None,
        "agent": None,
        "llm": None,
        "ok": False,
    }
    if not files:
        (dest / "原始文件分析.md").write_text("# 原始文件分析\n\n没有可送进模型的文本文件。\n", encoding="utf-8")

    write_workspace_agents(job_dir)

    from gameaihack.core.progress import log
    from gameaihack.core.fs import count_by_suffix
    from gameaihack.core.layout import art_dir, assets_dir
    from gameaihack.content.facts import write_fact_source

    log(f"[{via}] 解包已完成。agent 反编译玩法，并在 Maker 里做成游戏")
    from gameaihack.content.accept import accept_design, snapshot_protected

    snap = snapshot_protected(job_dir)
    book = run_book(job_dir, ir, cfg, via=via)
    result["agent"] = {
        "ok": book.get("ok"),
        "via": book.get("via"),
        "error": book.get("error"),
        "steps": book.get("steps"),
    }
    art = art_dir(job_dir)
    image = assets_dir(job_dir) / "image"
    n_png = count_by_suffix(image, ".png") if image.is_dir() else 0
    if n_png == 0:
        n_png = count_by_suffix(art, ".png") if art.is_dir() else 0
    if n_png == 0:
        log(f"[{via}] 还没有反编译贴图，抽资源补一次（gameaihack art）")
        from gameaihack.art.unity import ensure_game_art

        ensure_game_art(job_dir)
        write_fact_source(job_dir, ir)
        snap = snapshot_protected(job_dir)
    if book.get("ok"):
        gaps = accept_design(job_dir, snap)
        if gaps:
            fill = run_book(
                job_dir,
                ir,
                cfg,
                via=via,
                tasks=[("补缺口", gap_prompt(gaps))],
            )
            result["agent"]["steps"] = list(result["agent"].get("steps") or []) + list(fill.get("steps") or [])
            gaps = accept_design(job_dir, snap)
            if gaps:
                err = "策划未达到交差线：\n" + "\n".join(f"- {x}" for x in gaps)
                result["agent"]["ok"] = False
                result["agent"]["error"] = err
                book = result["agent"]
                log(f"[{via}] {err}")
            elif not fill.get("ok"):
                result["agent"]["ok"] = False
                result["agent"]["error"] = fill.get("error") or "补缺口失败"
                book = result["agent"]
            else:
                book = result["agent"]
    result["dsh"] = result["agent"]
    if book.get("ok"):
        result["ok"] = True
    elif book.get("error"):
        (dest / "agent.error.txt").write_text(str(book["error"]), encoding="utf-8")
    ir["ai_analysis"] = result
    return result
