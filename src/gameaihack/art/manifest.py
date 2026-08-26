"""Maker 工程资源清单：贴图和音在 assets/，给 scripts 引用。"""

from __future__ import annotations

import csv
import json
import struct
from collections import defaultdict
from pathlib import Path

from gameaihack.core.fs import iter_files

MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ogg", ".mp3", ".wav", ".m4a"}

ROLE = {
    "sprites": "场上会动的：玩家、抛体、目标、角色。Lua 里当 Sprite。",
    "world": "地形、障碍、背景。做物理场和关卡摆放。",
    "ui": "局内 HUD、按钮。不要拿去当商店图。",
    "fx": "命中、爆炸、拖尾。",
    "loose": "包里散落的 png。",
    "audio": "音效。",
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


def write_manifest(root: Path, ir: dict | None = None) -> dict:
    """root 可以是 output/assets 或 output/美术。"""
    root.mkdir(parents=True, exist_ok=True)
    rows = _scan(root)
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["folder"]].append(r)
    snap = {
        "package": ((ir or {}).get("package") or {}).get("name"),
        "total": len(rows),
        "folders": {k: len(v) for k, v in sorted(by.items())},
        "bytes": sum(r["bytes"] for r in rows),
    }
    dest = root / "清单"
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
    (dest / "给策划.md").write_text(_maker_md(snap, by, root), encoding="utf-8")
    (dest / "程序.md").write_text(_maker_md(snap, by, root), encoding="utf-8")
    (dest / "美术.md").write_text(_maker_md(snap, by, root), encoding="utf-8")
    (dest / "总览.md").write_text(_maker_md(snap, by, root), encoding="utf-8")
    (root / "catalog.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snap


def _scan(root: Path) -> list[dict]:
    rows: list[dict] = []
    for p in iter_files(root, skip_dirs={"清单"}):
        if p.name.startswith("."):
            continue
        suf = p.suffix.lower()
        if suf not in MEDIA:
            continue
        try:
            rel = p.relative_to(root).as_posix()
            folder = rel.split("/", 1)[0]
            if folder == "image" and "/" in rel:
                rest = rel.split("/", 1)[1]
                folder = rest.split("/", 1)[0]
            st = p.stat()
        except (OSError, ValueError):
            continue
        wh = png_size(p) if suf == ".png" else None
        rows.append(
            {
                "folder": folder,
                "path": rel,
                "ext": suf,
                "bytes": st.st_size,
                "width": wh[0] if wh else "",
                "height": wh[1] if wh else "",
            }
        )
    rows.sort(key=lambda r: (r["folder"], r["path"]))
    return rows


def _maker_md(snap: dict, by: dict, root: Path) -> str:
    name = snap.get("package") or ""
    lines = [
        f"# 反编译资源（Maker 用）· {name}\n",
        f"共 {snap.get('total') or 0} 个文件。路径相对 `{root.name}/`。\n",
        "在 `scripts/` 里引用：`assets/image/<桶>/...png`、`assets/audio/...`。\n",
        "这些是从原包解出来给 **TapTap Maker 做同一套玩法** 用的，不是运营素材墙。\n",
        "| 桶 | 数量 | 用途 |",
        "|---|---:|---|",
    ]
    for folder, items in sorted(by.items(), key=lambda x: str(x[0])):
        role = ROLE.get(folder) or "玩法资源"
        lines.append(f"| `{folder}` | {len(items)} | {role} |")
    lines.append("")
    lines.append("## 各桶样例\n")
    for folder, items in sorted(by.items(), key=lambda x: str(x[0])):
        lines.append(f"### {folder}\n")
        for r in items[:12]:
            lines.append(f"- `{r['path']}`")
        if len(items) > 12:
            lines.append(f"- … 还有 {len(items) - 12} 个")
        lines.append("")
    return "\n".join(lines) + "\n"
