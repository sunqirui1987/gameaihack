"""美术目录的资源总清单：给程序导入、给美术对照、给策划嵌图。"""

from __future__ import annotations

import csv
import json
import struct
from collections import defaultdict
from pathlib import Path

from gameaihack.core.fs import iter_files

SKIP_TOP = {"清单", "textures", "audio", "fonts", "maps", "video"}
MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ogg", ".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ttf", ".otf", ".fnt"}

ROLE = {
    "角色": "立绘 / 模型贴图 / 对战单位。程序按角色 id 引用，美术对照重绘。",
    "服装": "换装、皮肤。子目录往往是套装名。",
    "头像": "列表、个人页、结算用的小头像。",
    "头像框": "头像外框、装饰。",
    "界面": "HUD、弹窗、按钮、大厅。做新 UI 时按文件名对功能。",
    "场景": "关卡背景、主题场景、环境道具。",
    "关卡": "章节图、选关、进度。",
    "特效": "命中、爆炸、拖尾。新引擎用自己的粒子，这里只对照。",
    "道具": "消耗品、强化、宝箱。",
    "礼包": "商店、内购、活动包。",
    "奖励": "领奖、掉落展示。",
    "赛季": "通行证、赛季皮肤。",
    "公会": "公会、社交。",
    "表情": "聊天表情。",
    "加载": "闪屏、Loading、Logo。",
    "字体": "点阵字、艺术字。新游戏尽量用自己的字库。",
    "音频": "音效 / 短音乐。",
    "视频": "过场、广告创意。",
    "技术贴图": "法线、Mask、LUT。程序看，一般不用重绘成玩法图。",
    "其他": "尚未归类。制作前先扫一遍，能归的再挪。",
    "原始": "包内已是 png/ogg 的散文件，路径尽量保持原相对目录。",
}


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return int(w), int(h)


def write_manifest(art: Path, ir: dict | None = None) -> dict:
    art.mkdir(parents=True, exist_ok=True)
    rows = _scan(art)
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["folder"]].append(r)
    snap = {
        "package": ((ir or {}).get("package") or {}).get("name"),
        "total": len(rows),
        "folders": {k: len(v) for k, v in sorted(by.items())},
        "bytes": sum(r["bytes"] for r in rows),
    }
    dest = art / "清单"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "全部.json").write_text(
        json.dumps({"meta": snap, "files": rows}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (dest / "全部.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["folder", "path", "ext", "bytes", "width", "height"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) if r.get(k) is not None else "" for k in w.fieldnames})
    (dest / "总览.md").write_text(_overview_md(snap, by), encoding="utf-8")
    (dest / "程序.md").write_text(_code_md(snap, by), encoding="utf-8")
    (dest / "美术.md").write_text(_art_md(snap, by), encoding="utf-8")
    (dest / "给策划.md").write_text(_design_md(snap, by), encoding="utf-8")
    (art / "catalog.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (art / "catalog.md").write_text(
        f"# 美术清单\n\n完整清单在 [清单/总览.md](清单/总览.md)。"
        f"程序看 [清单/程序.md](清单/程序.md)，美术看 [清单/美术.md](清单/美术.md)。\n"
        f"机器表：[清单/全部.csv](清单/全部.csv)。\n",
        encoding="utf-8",
    )
    return snap


def _scan(art: Path) -> list[dict]:
    rows: list[dict] = []
    for p in iter_files(art, skip_dirs={"清单"}):
        if p.name.startswith("."):
            continue
        suf = p.suffix.lower()
        if suf not in MEDIA and suf != ".png":
            if suf in {".md", ".json", ".txt", ".csv"}:
                continue
        try:
            rel = p.relative_to(art).as_posix()
            size = p.stat().st_size
        except (ValueError, OSError):
            continue
        parts = Path(rel).parts
        folder = parts[0] if parts else "其他"
        if folder in SKIP_TOP and folder not in ROLE:
            folder = folder
        wh = png_size(p) if suf == ".png" else None
        rows.append(
            {
                "folder": folder,
                "path": rel,
                "ext": suf or "",
                "bytes": size,
                "width": wh[0] if wh else None,
                "height": wh[1] if wh else None,
            }
        )
    rows.sort(key=lambda r: (r["folder"], r["path"]))
    return rows


def _design_md(snap: dict, by: dict) -> str:
    pkg = snap.get("package") or ""
    lines = [
        f"# 美术清单（给策划）· {pkg}\n",
        "策划嵌图、图鉴、系统总表**只能用这些文件夹和代表文件**。不要发明目录。\n",
        "| 目录 | 数量 | 用途 | 代表文件（嵌图用这些 path） |",
        "|---|---:|---|---|",
    ]
    for name, items in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        samples = "、".join(f"`{x['path']}`" for x in items[:5])
        lines.append(f"| `{name}/` | {len(items)} | {ROLE.get(name, '待归类')} | {samples} |")
    lines += [
        "\n图鉴必须一篇对应一个目录，文件名与目录名相同，例如 `策划/图鉴/角色.md`。\n",
        "引用：`![](../美术/角色/xxx.png)`，path 必须能在 [全部.csv](全部.csv) 里找到。\n",
    ]
    return "\n".join(lines)


def _overview_md(snap: dict, by: dict) -> str:
    pkg = snap.get("package") or ""
    lines = [
        f"# 资源总清单 · {pkg}\n",
        "给**程序、美术、策划**用的同一份目录。图在上一级各文件夹，本文只索引。\n",
        f"合计 **{snap['total']}** 个文件，约 **{snap['bytes'] / (1024 * 1024):.1f} MB**。\n",
        "| 目录 | 数量 | 给谁 | 做什么 |",
        "|---|---:|---|---|",
    ]
    for name, items in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        who = "程序+美术" if name in {"界面", "角色", "服装", "场景"} else ("程序" if name == "技术贴图" else "美术+策划")
        lines.append(f"| [`{name}/`](../{name}/) | {len(items)} | {who} | {ROLE.get(name, '待归类')} |")
    lines += [
        "\n## 怎么用\n",
        "1. 程序：按 [程序.md](程序.md) 的目录当资源包结构，做新游戏时用自己的格式重新导入。",
        "2. 美术：按 [美术.md](美术.md) 对照重绘，不要把这些 PNG 当上架素材。",
        "3. 策划：图鉴和正文用 `![](../美术/<目录>/…)` 引用。",
        "4. 全表：[全部.csv](全部.csv) 可进表格软件筛选。\n",
    ]
    return "\n".join(lines)


def _code_md(snap: dict, by: dict) -> str:
    lines = [
        "# 程序用资源清单\n",
        "新游戏不要直接加载这些 PNG 上架。当作**命名、分类、对照尺寸**的规格。\n",
        "## 建议工程目录\n",
        "```",
        "Content/",
    ]
    for name in sorted(by):
        lines.append(f"  {name}/")
    lines += [
        "```\n",
        "## 各目录\n",
    ]
    for name, items in sorted(by.items()):
        png = [x for x in items if x["ext"] == ".png"]
        sizes = [(x["width"], x["height"]) for x in png if x.get("width")]
        sample = "、".join(f"`{Path(x['path']).name}`" for x in items[:6])
        dim = ""
        if sizes:
            dim = f"常见尺寸例如 {sizes[0][0]}×{sizes[0][1]}。"
        lines.append(f"### {name}/ （{len(items)}）\n")
        lines.append(f"{ROLE.get(name, '')} {dim}\n")
        lines.append(f"例：{sample}\n")
    lines.append("机器完整表见 [全部.csv](全部.csv)。\n")
    return "\n".join(lines)


def _art_md(snap: dict, by: dict) -> str:
    lines = [
        "# 美术用资源清单\n",
        "按文件夹对照重绘。每张图在新游戏里用自己的分层文件重做，这里只看构图、色彩、UI 切图范围。\n",
    ]
    for name, items in sorted(by.items()):
        if name == "技术贴图":
            continue
        lines.append(f"## {name}/ · {len(items)} 张\n")
        lines.append(f"{ROLE.get(name, '')}\n")
        lines.append("| 文件 | 尺寸 |")
        lines.append("|---|---|")
        for x in items[:40]:
            dim = f"{x['width']}×{x['height']}" if x.get("width") else "—"
            lines.append(f"| `{x['path']}` | {dim} |")
        if len(items) > 40:
            lines.append(f"\n其余 {len(items) - 40} 张见 CSV。\n")
        else:
            lines.append("")
    return "\n".join(lines)
