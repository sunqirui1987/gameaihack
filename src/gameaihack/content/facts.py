"""机器事实源：raw 清单 + 美术清单。策划只准引用这里有的东西。"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

from gameaihack.core.layout import art_dir, design_dir, extract_dir, ir_dir, raw_dir


def write_fact_source(job_dir: Path, ir: dict | None = None) -> Path:
    """写出 raw/清单、美术/清单/给策划.md、策划/_事实源.md。"""
    ir = ir or _load_ir(job_dir)
    art = art_dir(job_dir)
    from gameaihack.art.manifest import write_manifest

    if not (art / "清单" / "给策划.md").is_file():
        write_manifest(art, ir)
    else:
        _ensure_art_digest(art, ir)
    raw_md = write_raw_digest(job_dir, ir)
    art_md = art / "清单" / "给策划.md"
    design = design_dir(job_dir)
    design.mkdir(parents=True, exist_ok=True)
    body = _combine(job_dir, ir, raw_md, art_md)
    dest = design / "_事实源.md"
    dest.write_text(body, encoding="utf-8")
    _seed_gallery(design, art)
    write_job_inventory(job_dir, ir)
    return dest


def write_job_inventory(job_dir: Path, ir: dict | None = None) -> Path:
    """包名目录下的完整清单：jobs/<包>/清单.md 与 清单/。"""
    job_dir = Path(job_dir)
    ir = ir or _load_ir(job_dir)
    dest = job_dir / "清单"
    dest.mkdir(parents=True, exist_ok=True)
    art = art_dir(job_dir)
    design = design_dir(job_dir)
    raw = raw_dir(job_dir)
    for src, name in (
        (art / "清单" / "给策划.md", "美术.md"),
        (art / "清单" / "程序.md", "程序.md"),
        (art / "清单" / "美术.md", "美术对照.md"),
        (art / "清单" / "全部.csv", "美术全部.csv"),
        (raw / "清单" / "给策划.md", "raw.md"),
        (design / "_事实源.md", "事实源.md"),
    ):
        if src.is_file():
            shutil.copy2(src, dest / name)
    body = _job_index_md(job_dir, ir)
    (job_dir / "清单.md").write_text(body, encoding="utf-8")
    (dest / "README.md").write_text(
        "# 清单\n\n完整总览在上一级 [../清单.md](../清单.md)。\n\n"
        "- [raw.md](raw.md) 解包事实\n"
        "- [美术.md](美术.md) 美术给策划\n"
        "- [程序.md](程序.md) 程序导入\n"
        "- [美术对照.md](美术对照.md)\n"
        "- [事实源.md](事实源.md)\n"
        "- [美术全部.csv](美术全部.csv)\n",
        encoding="utf-8",
    )
    return job_dir / "清单.md"


def _job_index_md(job_dir: Path, ir: dict) -> str:
    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    fp = ir.get("fingerprint") or {}
    art = art_dir(job_dir)
    design = design_dir(job_dir)
    levels = ir.get("levels") or []
    tables = ir.get("tables") or []
    art_meta = {}
    cat = art / "清单" / "全部.json"
    if cat.is_file():
        try:
            art_meta = json.loads(cat.read_text(encoding="utf-8")).get("meta") or {}
        except (OSError, json.JSONDecodeError):
            art_meta = {}
    folders = art_meta.get("folders") or {}
    if not folders and art.is_dir():
        folders = {
            p.name: sum(1 for f in p.rglob("*") if f.is_file() and not f.name.startswith("."))
            for p in sorted(art.iterdir())
            if p.is_dir() and p.name != "清单" and not p.name.startswith(".")
        }
    art_rows = "\n".join(f"| `{k}/` | {v} |" for k, v in sorted(folders.items(), key=lambda x: str(x[0])))
    design_files = []
    if design.is_dir():
        for f in sorted(design.rglob("*.md")):
            if f.name.startswith(".") or f.name == "过程.md":
                continue
            design_files.append(f"`策划/{f.relative_to(design).as_posix()}`")
    des = "\n".join(f"- {x}" for x in design_files[:80]) or "- （尚未写策划）"
    norm = extract_dir(job_dir) / "normalized"
    extract_lines = []
    if norm.is_dir():
        for p in sorted(norm.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                extract_lines.append(f"| `{p.name}/` | {sum(1 for x in p.rglob('*') if x.is_file())} |")
    ext = "\n".join(extract_lines) or "| — | 0 |"
    return f"""# 清单 · {pkg}

本目录是这个包的**总清单**。做新游戏先读这一份，再进 `output/策划/` 和 `output/美术/`。

| | |
|---|---|
| 包名 | `{pkg}` |
| 原作引擎 | {fp.get("engine") or "—"} / {fp.get("script_backend") or "—"} |
| 关卡 | {len(levels)} |
| 表 | {len(tables)} |
| 美术文件 | {art_meta.get("total") or sum(int(v) if str(v).isdigit() else 0 for v in folders.values())} |

## 目录

| 路径 | 是什么 |
|---|---|
| [raw/](raw/) | 解包，只读 |
| [raw/清单/](raw/清单/) | raw 事实（表、关卡、引擎） |
| [output/美术/](output/美术/) | 抽出的对照图 |
| [output/美术/清单/](output/美术/清单/) | 美术总览 / 程序 / 美术 / 全部.csv |
| [output/策划/](output/策划/) | 制作说明书（按本清单写） |
| [output/策划/_事实源.md](output/策划/_事实源.md) | 策划必须遵守的合成事实源 |
| [run.log](run.log) | 运行日志 |

本文件夹里还有：[raw.md](清单/raw.md) · [美术.md](清单/美术.md) · [程序.md](清单/程序.md) · [事实源.md](清单/事实源.md) · [美术全部.csv](清单/美术全部.csv)

## 美术文件夹

| 目录 | 数量 |
|---|---:|
{art_rows or "| （空） | 0 |"}

## raw 抽出

| 目录 | 文件 |
|---|---:|
{ext}

## 策划文稿

{des}

## 怎么做新游戏

1. 读本清单和 [output/策划/_事实源.md](output/策划/_事实源.md)
2. 按 [output/策划/制作顺序.md](output/策划/制作顺序.md) 开工
3. 用 [output/策划/02-核心玩法.md](output/策划/02-核心玩法.md) 做第一局
4. 美术只对照 [output/美术/](output/美术/)；上架图生成到 [output/assets/image/](output/assets/image/)
5. 不要重打包原 APK
"""


def load_fact_source(job_dir: Path) -> str:
    path = design_dir(job_dir) / "_事实源.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def write_raw_digest(job_dir: Path, ir: dict) -> Path:
    dest = raw_dir(job_dir) / "清单"
    dest.mkdir(parents=True, exist_ok=True)
    text = _raw_md(job_dir, ir)
    path = dest / "给策划.md"
    path.write_text(text, encoding="utf-8")
    (dest / "总览.md").write_text(text, encoding="utf-8")
    meta = {
        "package": (ir.get("package") or {}).get("name"),
        "engine": (ir.get("fingerprint") or {}).get("engine"),
        "levels": len(ir.get("levels") or []),
        "tables": len(ir.get("tables") or []),
    }
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _ensure_art_digest(art: Path, ir: dict | None) -> None:
    path = art / "清单" / "给策划.md"
    if path.is_file() and path.stat().st_size > 20:
        return
    from gameaihack.art.manifest import write_manifest

    write_manifest(art, ir)


def _load_ir(job_dir: Path) -> dict:
    p = ir_dir(job_dir) / "game.ir.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _combine(job_dir: Path, ir: dict, raw_md: Path, art_md: Path) -> str:
    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    raw_txt = raw_md.read_text(encoding="utf-8") if raw_md.is_file() else "（raw 清单未生成）"
    art_txt = art_md.read_text(encoding="utf-8") if art_md.is_file() else "（美术清单未生成）"
    folders = _art_folders(art_dir(job_dir))
    gallery = "、".join(f"图鉴/{n}.md" for n in folders) or "（还没有美术目录）"
    return (
        f"# 事实源 · {pkg}\n\n"
        "机器根据 **raw/** 和 **output/美术/** 生成。策划正文必须遵守。\n\n"
        "- 系统、表、关卡：只写下面「raw 清单」里有的；没有的标未知\n"
        "- 目录和图：只引用「美术清单」里的文件夹和代表文件，禁止发明目录名\n"
        f"- 图鉴必须按文件夹各写一篇：{gallery}\n"
        "- 嵌图路径用 `![](../美术/<清单里的 path>)`\n"
        "- 不要改本文件\n\n"
        "---\n\n"
        f"{art_txt}\n\n---\n\n{raw_txt}\n"
    )


def _art_folders(art: Path) -> list[str]:
    skip = {"清单", "textures", "audio", "fonts", "maps", "video"}
    if not art.is_dir():
        return []
    return sorted(
        p.name
        for p in art.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in skip
    )


def _seed_gallery(design: Path, art: Path) -> None:
    folders = _art_folders(art)
    dest = design / "图鉴"
    dest.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| {n} | [图鉴/{n}.md]({n}.md) | [../美术/{n}/](../../美术/{n}/) |" for n in folders)
    (dest / "README.md").write_text(
        "# 图鉴\n\n"
        "按 **美术清单** 的文件夹建篇。不要改文件夹名。\n\n"
        "| 清单目录 | 本篇 | 美术 |\n|---|---|---|\n"
        f"{rows or '| （空） | | |'}\n",
        encoding="utf-8",
    )


def _raw_md(job_dir: Path, ir: dict) -> str:
    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    fp = ir.get("fingerprint") or {}
    levels = ir.get("levels") or []
    tables = ir.get("tables") or []
    loc = ir.get("loc") or {}
    claims = ir.get("claims") or []
    chs = sorted(
        {
            int((lv.get("extra") or {}).get("chapter"))
            for lv in levels
            if (lv.get("extra") or {}).get("chapter") is not None
            and str((lv.get("extra") or {}).get("chapter")).isdigit()
        }
    )
    kinds = Counter((r.get("kind") or "other") for r in (ir.get("resources") or []))
    lines = [
        f"# raw 清单 · {pkg}\n",
        "给策划用的**解包事实**。玩法、表、关卡只能写这里有的。\n",
        "| | |",
        "|---|---|",
        f"| 引擎 | {fp.get('engine') or '—'} / {fp.get('script_backend') or '—'} |",
        f"| 版本 | {(ir.get('package') or {}).get('version_name') or '—'} |",
        f"| 关卡 | {len(levels)} 关 / {len(chs)} 章 |",
        f"| 表 | {len(tables)} |",
        f"| 语言 | {', '.join(loc.get('languages') or []) or '—'} |",
        "",
        "## 必读文件\n",
        "- `raw/ir/game.ir.json`",
        "- `raw/ir/levels_index.json`",
        "- `raw/ir/tables_index.json`",
        "- `raw/fingerprint.json`",
        "- `raw/extract/normalized/` 配置和脚本\n",
        "## 表\n",
        "| id | 角色 | 行数 |",
        "|---|---|---:|",
    ]
    for t in tables[:80]:
        lines.append(f"| `{t.get('id') or ''}` | {t.get('role') or '—'} | {t.get('row_count') or t.get('rows') or ''} |")
    if not tables:
        lines.append("| （无） | | |")
    lines += ["\n## 资源种类（IR）\n", "| 种类 | 数量 |", "|---|---:|"]
    for k, n in sorted(kinds.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"| {k} | {n} |")
    if not kinds:
        lines.append("| — | 0 |")
    lines.append("\n## 抽出目录\n")
    norm = extract_dir(job_dir) / "normalized"
    if norm.is_dir():
        for p in sorted(norm.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                n = sum(1 for _ in p.rglob("*") if _.is_file())
                lines.append(f"- `{p.name}/` {n} 个文件")
    else:
        lines.append("（还没有 extract/normalized）")
    lines.append("\n## 机器主张（核对用，以文件为准）\n")
    for c in claims[:20]:
        t = str(c.get("text") or "").strip()
        if t:
            lines.append(f"- {t}")
    if not claims:
        lines.append("- （无）")
    unks = ir.get("unknowns") or []
    if unks:
        lines.append("\n## 未知\n")
        for u in unks[:20]:
            lines.append(f"- {u}")
    lines.append("")
    return "\n".join(lines)
