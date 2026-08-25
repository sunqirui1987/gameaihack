"""制作材料包：策划是开工说明书，美术是对照图。"""

from __future__ import annotations

import json
from pathlib import Path

from gameaihack.core.layout import art_dir, design_dir, output_dir

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

    n_png = count_by_suffix(art, ".png") if art.is_dir() else 0
    folders = sorted(
        p.name
        for p in (art.iterdir() if art.is_dir() else [])
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
        can.append("画面对照（立绘 / UI / 场景贴图）")
    else:
        need.append("抽出游戏贴图")
    if "02-核心玩法.md" in chapters:
        can.append("按策划搭核心循环")
    else:
        need.append("agent 写出核心玩法")
    if gallery:
        can.append("按图鉴把图对到系统")
    else:
        need.append("图鉴（策划/图鉴）")
    if n_lv:
        can.append(f"按 {n_lv} 关的编号排主线")
    else:
        need.append("关卡索引")
    if l2:
        can.append("部分关卡有几何，可对照摆关")
    else:
        need.append("关卡几何（坐标/布局）——当前只有编号")
    need.append("数值、动画、音效、物理参数需在自己的引擎里重做")
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
    (job_dir / "README.md").write_text(
        f"# {pkg}\n\n"
        "这是一份**新游戏制作材料包**。先打开 **[清单.md](清单.md)**。\n\n"
        "用策划当制作说明书，用美术当对照图，在自己的引擎里重做。不要重打包原 APK。\n\n"
        "| 目录 | 是什么 |\n|---|---|\n"
        "| [清单.md](清单.md) | **总清单**（包名下一份完整索引） |\n"
        "| [清单/](清单/) | raw / 美术 / 程序 / 事实源 |\n"
        "| [raw/](raw/) | 解包，不外发 |\n"
        "| [output/策划/](output/策划/) | 制作说明书 |\n"
        "| [output/美术/](output/美术/) | 对照图 |\n"
        "| [run.log](run.log) | 运行日志 |\n",
        encoding="utf-8",
    )
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
    return f"""# 复刻说明 · {pkg}

这是**制作说明书 + 对照图**。用自己的引擎做一款玩法相同的新游戏。不要重打包原 APK。美术只当样子。

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

1. [策划/_事实源.md](策划/_事实源.md)（raw 清单 + 美术清单，策划按这个写）
2. [策划/制作顺序.md](策划/制作顺序.md)（没有就先看 README）
3. [策划/02-核心玩法.md](策划/02-核心玩法.md) 做出第一局
3. [策划/图鉴/](策划/图鉴/) 把 PNG 对到角色、界面、场景
4. [策划/07-新手-UI-社交.md](策划/07-新手-UI-社交.md) 搭大厅和屏幕流
5. [策划/关卡/](策划/关卡/) 按编号排主线；没有几何的关只做节奏
6. 成长、经济、活动按 04 / 05 / 06 补

完整度机器记录：[完整度.json](完整度.json)。
"""
