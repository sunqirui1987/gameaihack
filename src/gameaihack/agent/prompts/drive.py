"""组装全程任务。正文只来自 mission.py。"""

from __future__ import annotations

from pathlib import Path

from gameaihack.agent.prompts.mission import DRIVE, PERSONA  # noqa: F401

__all__ = ["PERSONA", "DRIVE", "drive_tasks", "gap_prompt"]


def _ir_brief(ir: dict) -> str:
    fp = ir.get("fingerprint") or {}
    genre = (ir.get("genre_guess") or {}).get("id") or "未判定"
    n_lv = len(ir.get("levels") or [])
    n_tb = len(ir.get("tables") or [])
    n_res = len(ir.get("resources") or [])
    claims = ir.get("claims") or []
    bits = []
    for c in claims[:12]:
        t = str(c.get("text") or "").strip()
        if t:
            bits.append(f"- {t}")
    claim_txt = "\n".join(bits) or "- （IR 尚无主张）"
    return (
        f"引擎 {fp.get('engine') or '—'} / {fp.get('script_backend') or '—'}，"
        f"品类猜测 {genre}，关卡 {n_lv}，表 {n_tb}，资源 {n_res}。\n\n"
        f"机器已抽出的主张（供核对；商业化可忽略）：\n{claim_txt}\n"
    )


def drive_tasks(job_dir: Path, ir: dict) -> list[tuple[str, str]]:
    from gameaihack.content.facts import load_fact_source, write_fact_source

    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    facts = load_fact_source(job_dir)
    if not facts.strip():
        write_fact_source(job_dir, ir)
        facts = load_fact_source(job_dir)
    if len(facts) > 12000:
        facts = facts[:12000] + "\n\n（事实源过长，已截断。完整见 output/策划/_事实源.md）\n"
    prompt = (
        DRIVE
        + f"\n游戏 `{pkg}`。\n"
        + _ir_brief(ir)
        + "\n## 事实源摘录\n\n"
        + facts
        + "\n\n先提取美术（`gameaihack art .`），再提取策划（`02-核心玩法.md`），"
        "然后把一模一样的玩法写进 `scripts/main.lua`。不要只交文档。\n"
    )
    return [("全程", prompt)]


def gap_prompt(gaps: list[str]) -> str:
    return (
        "还没做成玩法一模一样的新游戏，缺：\n"
        + "\n".join(f"- {x}" for x in gaps)
        + "\n顺序：提取美术 `gameaihack art .` → 把 02 写成完整游戏 PRD → "
        "按 PRD 在 `scripts/main.lua` 用 `assets/image/` 实现同一套玩法。"
        "02 必须非常详细（核心循环、操作规格、每个场上物、规则、第一关、验收）。"
        "不要补商业化。不要建 tests/。\n"
    )
