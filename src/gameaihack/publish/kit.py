"""封口：提取出的策划+美术，以及 Maker 里的新游戏。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from gameaihack.core.layout import art_dir, assets_dir, design_dir, output_dir

def harvest_design(job_dir: Path) -> int:
    """把写到错误位置的策划 md 收到 output/策划。"""
    dest = output_dir(job_dir) / "策划"
    dest.mkdir(parents=True, exist_ok=True)
    dest_r = dest.resolve()
    n = 0
    for src in (job_dir / "game" / "策划", job_dir / "策划"):
        if not src.is_dir():
            continue
        try:
            if src.resolve() == dest_r:
                continue
        except OSError:
            continue
        for f in src.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in {".md", ".txt"}:
                continue
            out = dest / f.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out)
            n += 1
    return n


CORE_DESIGN = (
    "00-封面.md",
    "01-产品定位.md",
    "02-核心玩法.md",
    "03-关卡设计.md",
    "04-成长与进度.md",
    "05-经济与商业化.md",
    "06-系统总表.md",
    "07-新手-UI-社交.md",
    "08-技术约束.md",
    "09-未知与下一步.md",
)


def inspect_kit(job_dir: Path, ir: dict | None = None) -> dict:
    """看 output/ 里复刻材料齐不齐。不针对某一款游戏。"""
    out = output_dir(job_dir)
    design = design_dir(job_dir)
    art = art_dir(job_dir)
    ir = ir or {}
    from gameaihack.core.fs import count_by_suffix

    image = assets_dir(job_dir) / "image"
    n_png = count_by_suffix(image, ".png") if image.is_dir() else 0
    if n_png == 0:
        n_png = count_by_suffix(art, ".png") if art.is_dir() else 0
    src = image if n_png else art
    folders = sorted(
        p.name
        for p in (src.iterdir() if src.is_dir() else [])
        if p.is_dir() and not p.name.startswith(".") and p.name not in {"textures", "audio", "fonts", "maps", "video", "清单"}
    )
    chapters = [fn for fn in CORE_DESIGN if (design / fn).is_file()]
    gallery = (design / "图鉴" / "README.md").is_file()
    levels = ir.get("levels") or []
    l2 = sum(1 for lv in levels if str(lv.get("rebuild_grade") or "L0") >= "L2")
    n_ch = len(
        {
            (lv.get("extra") or {}).get("chapter")
            for lv in levels
            if (lv.get("extra") or {}).get("chapter") is not None
        }
    )
    return {
        "output": str(out),
        "art": {"png": n_png, "folders": folders},
        "design": {
            "core": chapters,
            "core_missing": [fn for fn in CORE_DESIGN if fn not in chapters],
            "gallery": gallery,
            "level_docs": len(list((design / "关卡").glob("*.md"))) if (design / "关卡").is_dir() else 0,
        },
        "levels": {"indexed": len(levels), "chapters": n_ch, "geometry_l2_plus": l2},
        "remake": _remake_verdict(n_png, chapters, len(levels), l2, gallery),
    }


def _remake_verdict(n_png: int, chapters: list[str], n_lv: int, l2: int, gallery: bool) -> dict:
    """对照重做能做到哪一步。"""
    can = []
    need = []
    if n_png:
        can.append("美术已提取到 assets/image")
    else:
        need.append("提取美术（gameaihack art .）")
    if "02-核心玩法.md" in chapters:
        can.append("核心玩法 PRD 已有文件")
    else:
        need.append("写出 02-核心玩法.md（游戏 PRD 设计稿）")
    if gallery:
        can.append("图鉴已对上提取的图")
    else:
        need.append("图鉴")
    if n_lv:
        can.append(f"关卡表 {n_lv} 关")
    else:
        need.append("关卡表")
    if l2:
        can.append("部分关有几何")
    need.append("按 PRD 把同一套玩法写进 scripts/main.lua")
    return {
        "can": can,
        "need": need,
        "same_look": bool(n_png and gallery),
        "same_systems": "02-核心玩法.md" in chapters,
        "same_levels": l2 > 0,
    }


def seal_kit(job_dir: Path, ir: dict) -> dict:
    """封口 output/：写复刻说明和完整度，不覆盖 agent 策划正文。"""
    snap = inspect_kit(job_dir, ir)
    out = output_dir(job_dir)
    (out / "完整度.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "复刻说明.md").write_text(_guide_md(job_dir, ir, snap), encoding="utf-8")
    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    from gameaihack.agent.prompts.mission import job_readme

    (job_dir / "README.md").write_text(job_readme(pkg), encoding="utf-8")
    return snap


def _guide_md(job_dir: Path, ir: dict, snap: dict) -> str:
    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    fp = ir.get("fingerprint") or {}
    rem = snap["remake"]
    art = snap["art"]
    des = snap["design"]
    lv = snap["levels"]
    can = "\n".join(f"- {x}" for x in rem["can"])
    need = "\n".join(f"- {x}" for x in rem["need"])
    folders = "、".join(f"`{x}`" for x in art["folders"]) or "（尚未分类）"
    order = (design_dir(job_dir) / "制作顺序.md").is_file()
    from gameaihack.agent.prompts.mission import GOAL, INIT_CMD, INSTALL_CMD

    return f"""# 复刻说明 · {pkg}

{GOAL}

本目录就是 Maker 工程。不要重打包原 APK。

| | |
|---|---|
| 引擎（原作） | {fp.get("engine") or "—"} |
| 贴图 | {art["png"]} 张 · {folders} |
| 策划章 | {len(des["core"])}/10 |
| 制作顺序 | {"有" if order else "无"} |
| 图鉴 | {"有" if des["gallery"] else "无"} |
| 关卡索引 | {lv["indexed"]} 关 / {lv["chapters"]} 章 |
| 关卡几何 | {lv["geometry_l2_plus"]} 关有布局 |

## 现在能对照着做

{can}

## 还要自己补

{need}

## 建议制作顺序

1. 安装 MCP：`{INSTALL_CMD}`
2. 本目录若还没有 `.project`：`{INIT_CMD}`
3. 读 [策划/02-核心玩法.md](策划/02-核心玩法.md)（提取出的玩法）
4. 用 [assets/image/](assets/image/) 的图，把同一套玩法写进 `scripts/main.lua`
5. `maker_build` 预览。先做出能打完的一局，再按 [策划/关卡/](策划/关卡/) 加关

完整度机器记录：[完整度.json](完整度.json)。
"""
