"""策划交差标准。agent 说完成不算数，缺文件或缺保护文件被改就失败。"""

from __future__ import annotations

from pathlib import Path

from gameaihack.core.fs import sha256_path
from gameaihack.core.layout import art_dir, design_dir, ir_dir
from gameaihack.publish.kit import CORE_DESIGN

GALLERY_OPTIONAL = {"技术贴图", "原始"}
# 不卡商业化。核心玩法必须写够，否则不算复制出玩法。
SKIP_DESIGN = {"05-经济与商业化.md"}
MIN_CORE = {
    "02-核心玩法.md": 5000,
    "03-关卡设计.md": 400,
    "制作顺序.md": 80,
    "README.md": 80,
}
MIN_LEVELS = 80
MIN_DEFAULT = 80


def _text_len(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").strip())
    except OSError:
        return 0


def art_gallery_folders(job_dir: Path) -> list[str]:
    from gameaihack.content.facts import _art_folders

    return [n for n in _art_folders(art_dir(job_dir)) if n not in GALLERY_OPTIONAL]


def missing_design(job_dir: Path) -> list[str]:
    """缺哪篇、哪篇太短。空列表表示达到交差线。"""
    design = design_dir(job_dir)
    miss: list[str] = []
    for name in CORE_DESIGN:
        if name in SKIP_DESIGN:
            continue
        n = _text_len(design / name)
        need = MIN_CORE.get(name, MIN_DEFAULT)
        if n < need:
            miss.append(f"策划/{name}（{n} 字，至少 {need}）")
    for name in ("README.md", "制作顺序.md"):
        n = _text_len(design / name)
        need = MIN_CORE[name]
        if n < need:
            miss.append(f"策划/{name}（{n} 字，至少 {need}）")
    n_lv = _text_len(design / "关卡" / "README.md")
    if n_lv < MIN_LEVELS:
        miss.append(f"策划/关卡/README.md（{n_lv} 字，至少 {MIN_LEVELS}）")
    play = (design / "02-核心玩法.md").read_text(encoding="utf-8", errors="replace") if (design / "02-核心玩法.md").is_file() else ""
    from gameaihack.agent.prompts.mission import PRD_NEEDLES

    for label, needles in PRD_NEEDLES:
        if not any(n in play for n in needles):
            miss.append(f"策划/02-核心玩法.md 还不是 PRD：缺「{label}」")
    gallery = design / "图鉴"
    for folder in art_gallery_folders(job_dir):
        path = gallery / f"{folder}.md"
        n = _text_len(path)
        if n < MIN_DEFAULT:
            miss.append(f"策划/图鉴/{folder}.md（{n} 字，至少 {MIN_DEFAULT}）")
    return miss


def snapshot_protected(job_dir: Path) -> dict:
    """agent 开跑前冻结事实源 / 美术清单 / IR。"""
    job = Path(job_dir)
    fact = design_dir(job) / "_事实源.md"
    ir = ir_dir(job) / "game.ir.json"
    art_md = art_dir(job) / "清单" / "给策划.md"
    art = art_dir(job)
    n_png = 0
    if art.is_dir():
        n_png = sum(1 for p in art.rglob("*.png") if p.is_file())
    return {
        "fact": sha256_path(fact) if fact.is_file() else "",
        "ir": sha256_path(ir) if ir.is_file() else "",
        "art_md": sha256_path(art_md) if art_md.is_file() else "",
        "art_png": n_png,
    }


def protected_violations(job_dir: Path, snap: dict) -> list[str]:
    now = snapshot_protected(job_dir)
    bad: list[str] = []
    if now.get("fact") != (snap or {}).get("fact"):
        bad.append("改了 output/策划/_事实源.md")
    if now.get("ir") != (snap or {}).get("ir"):
        bad.append("改了 raw/ir/game.ir.json")
    if now.get("art_md") != (snap or {}).get("art_md"):
        bad.append("改了 output/美术/清单/给策划.md")
    if int(now.get("art_png") or 0) != int((snap or {}).get("art_png") or 0):
        bad.append(
            f"美术 PNG 数量从 {(snap or {}).get('art_png')} 变成 {now.get('art_png')}"
        )
    return bad


def missing_maker_game(job_dir: Path) -> list[str]:
    """成品必须是 Maker 里能玩的同一套核心玩法，不是只有文档。"""
    from gameaihack.core.fs import count_by_suffix
    from gameaihack.core.layout import assets_dir, output_dir

    miss: list[str] = []
    image = assets_dir(job_dir) / "image"
    n = count_by_suffix(image, ".png") if image.is_dir() else 0
    if n == 0:
        miss.append("output/assets/image 没有反编译贴图（执行 gameaihack art .）")
    main = output_dir(job_dir) / "scripts" / "main.lua"
    body = _text_len(main)
    text = ""
    if main.is_file():
        try:
            text = main.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    if body < 400 or "function Start" not in text:
        miss.append("scripts/main.lua 还没有实现核心玩法（至少第一关能打完）")
    return miss


def accept_design(job_dir: Path, snap: dict | None = None) -> list[str]:
    """保护文件 + 玩法说明书 + Maker 游戏。都过才算成功。"""
    bad: list[str] = []
    if snap:
        bad.extend(protected_violations(job_dir, snap))
    bad.extend(missing_design(job_dir))
    bad.extend(missing_maker_game(job_dir))
    return bad
