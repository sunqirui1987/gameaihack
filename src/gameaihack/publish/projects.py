"""把 job 目录写成完整工程：策划文档 + 美术资源。"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from gameaihack.publish.gamebook import write_gamebook
from gameaihack.core.layout import (
    art_dir,
    design_dir,
    extract_dir,
    game_dir,
    ir_dir,
    migrate_game_to_output,
    output_dir,
    raw_dir,
    unpack_dir,
)
from gameaihack.core.paths import templates_dir
from gameaihack.art.unity import rip_unity_art

_SKIP_SUFFIX = {".apk", ".xapk", ".apks", ".aab", ".obb", ".so", ".dll", ".exe", ".dylib"}

ART_BUCKETS = ("textures", "audio", "fonts", "maps", "video")
DATA_BUCKETS = ("configs", "scripts")
MAX_RESOURCE_BYTES = 80 * 1024 * 1024

# share 只打 game/。raw/ 是解包，不外发。
PRODUCT_FILES = ("AGENTS.md", "README.md", "COVER.md", "LEGAL.txt")
PRODUCT_DIRS = ("策划", "美术", "data", "diagrams", "html")


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(templates_dir())),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
    )


def write_ai_projects(
    job_dir: Path, ir: dict, ctx: dict, *, overwrite_design: bool = True
) -> tuple[Path, Path]:
    """写出 output/（策划稿 + 美术）。raw/ 保持不动。

    overwrite_design=False 时保留 agent 已经写好的策划，只补美术清单和根 README。
    """
    migrate_game_to_output(job_dir)
    game = game_dir(job_dir)
    design = design_dir(job_dir)
    art = art_dir(job_dir)
    copied_art, copied_data = _copy_extracted(job_dir, art, game / "data")
    merged = unpack_dir(job_dir) / "merged"
    unity_ready = any(
        p.is_file() and p.suffix.lower() == ".png" and p.parent != art / "textures"
        for p in art.rglob("*.png")
    )
    if merged.is_dir() and not unity_ready:
        rip_unity_art(merged, art)
    seen_paths = {c.get("path") for c in copied_art}
    for p in art.rglob("*.png"):
        rel = p.relative_to(art).as_posix()
        if rel in seen_paths:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        copied_art.append(
            {
                "bucket": Path(rel).parts[0] if Path(rel).parts else "textures",
                "path": rel,
                "bytes": size,
                "kind": "texture",
            }
        )
    ctx = dict(ctx)
    ctx["_design_dir"] = str(design)
    if overwrite_design:
        _write_design(job_dir, design, ir, ctx)
        write_gamebook(design, ir, ctx)
    _write_data_files(job_dir, ir, ctx, data_root=game / "data")
    _write_art_catalog(art, ir, copied_art)
    _write_root(job_dir, ir, ctx, n_files=len(copied_art), dsh_final=not overwrite_design)
    _ = copied_data
    return design, art


def harvest_dsh(job_dir: Path) -> int:
    """把 agent 写在 game/策划、./策划 等处的 markdown 收口到 output/策划。"""
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


def _write_root(job_dir: Path, ir: dict, ctx: dict, *, n_files: int, dsh_final: bool = False) -> None:
    env = _env()
    c = dict(ctx)
    c["n_files"] = n_files
    game = game_dir(job_dir)
    game.mkdir(parents=True, exist_ok=True)
    pkg = c.get("package_name") or job_dir.name
    note = "策划由 agent 根据 raw/ 写成，这是最终稿。" if dsh_final else "先打开 output/策划。"
    (job_dir / "README.md").write_text(
        (
            f"# {pkg}\n\n"
            f"{c.get('one_liner') or ''}\n\n"
            "| 目录 | 是什么 |\n|---|---|\n"
            "| [raw/](raw/) | 解包后的原始数据（给 agent 读） |\n"
            "| [output/](output/) | **最终成品**：策划稿 + 美术 |\n\n"
            f"{note}\n\n"
            "先打开 [output/策划/00-封面.md](output/策划/00-封面.md)。\n"
        ),
        encoding="utf-8",
    )
    (game / "AGENTS.md").write_text(env.get_template("agents_job.md.j2").render(**c), encoding="utf-8")
    (game / "README.md").write_text(env.get_template("project_readme.md.j2").render(**c), encoding="utf-8")
    deliverable = raw_dir(job_dir) / "deliverable"
    _copy_if(deliverable / "COVER.md", game / "COVER.md")
    _copy_if(deliverable / "LEGAL.txt", game / "LEGAL.txt")
    html = game / "html"
    html.mkdir(exist_ok=True)
    _copy_if(deliverable / "index.html", html / "index.html")
    art = art_dir(job_dir)
    (art / "README.md").write_text(env.get_template("resources_readme.md.j2").render(**c), encoding="utf-8")
    (art / "AGENTS.md").write_text(env.get_template("agents_resources.md.j2").render(**c), encoding="utf-8")
    raw = raw_dir(job_dir)
    (raw / "README.md").write_text(
        (
            f"# raw · {pkg}\n\n"
            "解包后的原始工程。agent 分析的输入就是这里。\n\n"
            "- `unpacked/` APK/XAPK 解开\n"
            "- `extract/normalized/` 抽出的图音配置\n"
            "- `ir/` 机器 IR\n\n"
            "不要把这一层发给别人。成品在 `../output/`。\n"
        ),
        encoding="utf-8",
    )
    (raw / "AGENTS.md").write_text(
        (
            "# AGENTS.md — raw\n\n"
            "你在分析一个已解包的 Android 游戏。只读本目录。\n"
            "不要碰 apk/so/dex。把完整中文策划稿写到 `../output/策划/`。\n"
            "写给人看的 GDD：不要类名、不要路径、不要「来源」。\n"
            "PNG 已在 `../output/美术/`，用 markdown 图片引用。\n"
        ),
        encoding="utf-8",
    )


def _write_design(job_dir: Path, dest: Path, ir: dict, ctx: dict) -> None:
    for sub in ("gdd", "关卡", "系统"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    deliverable = raw_dir(job_dir) / "deliverable"
    _copy_if(deliverable / "COVER.md", dest / "COVER.md")
    design_src = deliverable / "design"
    if design_src.is_dir():
        for p in design_src.glob("*.md"):
            shutil.copy2(p, dest / "gdd" / p.name)
        unk = dest / "gdd" / "09-未知项.md"
        if unk.exists():
            shutil.copy2(unk, dest / "未知项.md")
    feel = deliverable / "feel" / "inventory.md"
    if feel.exists():
        shutil.copy2(feel, dest / "系统" / "feel.md")
    gallery = deliverable / "levels" / "gallery.md"
    if gallery.exists():
        shutil.copy2(gallery, dest / "关卡" / "gallery.md")
    (dest / "架构.md").write_text(_architecture_md(ir, ctx), encoding="utf-8")
    (dest / "关卡" / "README.md").write_text(_levels_readme(ir, ctx), encoding="utf-8")
    (dest / "README.md").write_text(
        (
            f"# 策划文档 · {ctx.get('package_name')}\n\n"
            f"{ctx.get('one_liner') or ''}\n\n"
            f"- [COVER.md](COVER.md) 一页纸\n"
            f"- [架构.md](架构.md)\n"
            f"- [gdd/](gdd/) 全书\n"
            f"- [关卡/](关卡/)\n"
            f"- [系统/](系统/) 手感\n"
            f"- [未知.md](未知.md) 还没还原的\n"
            f"- [封面.md](封面.md) 一页纸\n"
            f"- 数值表在 [`../data/tables/`](../data/tables/)\n"
        ),
        encoding="utf-8",
    )
    diagrams = game_dir(job_dir) / "diagrams"
    diagrams.mkdir(exist_ok=True)
    src = deliverable / "diagrams"
    if src.is_dir():
        for p in src.glob("*"):
            if p.is_file():
                shutil.copy2(p, diagrams / p.name)


def _write_data_files(job_dir: Path, ir: dict, ctx: dict, data_root: Path | None = None) -> None:
    data = data_root or (game_dir(job_dir) / "data")
    for sub in ("levels", "tables", "specs"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    (data / "README.md").write_text(_data_readme(), encoding="utf-8")
    ir_src = ir_dir(job_dir) / "game.ir.json"
    if ir_src.exists():
        shutil.copy2(ir_src, data / "game.ir.json")
    else:
        (data / "game.ir.json").write_text(
            json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    (data / "claims.json").write_text(
        json.dumps(ir.get("claims") or [], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (data / "radar.json").write_text(
        json.dumps(ir.get("radar") or [], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (data / "coverage.json").write_text(
        json.dumps(ir.get("coverage") or {}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    levels = ir.get("levels") or []
    index = []
    for lv in levels:
        extra = lv.get("extra") or {}
        index.append(
            {
                "id": lv.get("id"),
                "chapter": extra.get("chapter"),
                "level": extra.get("level"),
                "grade": lv.get("rebuild_grade"),
                "name": lv.get("name"),
            }
        )
    (data / "levels" / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    import csv

    idx_csv = data / "levels" / "index.csv"
    with idx_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["chapter", "level", "id", "grade", "name"])
        w.writeheader()
        for row in index:
            w.writerow({k: row.get(k) if row.get(k) is not None else "" for k in w.fieldnames})
    tables_src = raw_dir(job_dir) / "deliverable" / "tables"
    if tables_src.is_dir():
        for p in tables_src.glob("*"):
            if p.is_file():
                shutil.copy2(p, data / "tables" / p.name)
    fp = ir.get("fingerprint") or {}
    pkg = ir.get("package") or {}
    (data / "specs" / "identity.json").write_text(
        json.dumps(
            {
                "package": pkg.get("name"),
                "version_name": pkg.get("version_name"),
                "version_code": pkg.get("version_code"),
                "engine": fp.get("engine"),
                "script_backend": fp.get("script_backend"),
                "engine_version": fp.get("engine_version"),
                "protection": fp.get("protection") or [],
                "hotupdate": fp.get("hotupdate") or [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (data / "specs" / "loops.json").write_text(
        json.dumps(ir.get("loops") or {}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (data / "specs" / "genre.json").write_text(
        json.dumps(ir.get("genre_guess") or {}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _ = ctx


def _copy_extracted(job_dir: Path, art: Path, data: Path) -> tuple[list[dict], list[dict]]:
    art.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    for bucket in ART_BUCKETS:
        (art / bucket).mkdir(exist_ok=True)
    for bucket in DATA_BUCKETS:
        (data / bucket).mkdir(exist_ok=True)
    src_root = extract_dir(job_dir) / "normalized"
    copied_art: list[dict] = []
    copied_data: list[dict] = []
    mapping = [(b, art / b, copied_art) for b in ART_BUCKETS] + [
        (b, data / b, copied_data) for b in DATA_BUCKETS
    ]
    from gameaihack.core.fs import iter_files

    for bucket, dest, bag in mapping:
        src = src_root / bucket
        if not src.is_dir():
            continue
        for f in iter_files(src):
            if f.suffix.lower() in _SKIP_SUFFIX:
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if size > MAX_RESOURCE_BYTES:
                continue
            rel = f.relative_to(src)
            _place(f, dest / rel)
            bag.append({"bucket": bucket, "path": f"{dest.name}/{rel.as_posix()}", "bytes": size})
    return copied_art, copied_data


def _write_art_catalog(art: Path, ir: dict, copied: list[dict]) -> None:
    from gameaihack.art.manifest import write_manifest

    write_manifest(art, ir)
    _ = copied


def _architecture_md(ir: dict, ctx: dict) -> str:
    fp = ir.get("fingerprint") or {}
    loops = ir.get("loops") or {}

    def chain(key: str) -> str:
        items = loops.get(key) or []
        ids = [x.get("id", "") for x in items if isinstance(x, dict)]
        return " → ".join(ids) or "未还原"

    prot = ", ".join(fp.get("protection") or []) or "none"
    hot = ", ".join(fp.get("hotupdate") or []) or "none"
    return (
        f"# 架构\n\n"
        f"{ctx.get('one_liner') or ''}\n\n"
        f"| 项 | 值 |\n|---|---|\n"
        f"| 包名 | `{ctx.get('package_name')}` |\n"
        f"| 引擎 | {fp.get('engine')} / {fp.get('script_backend') or '—'} |\n"
        f"| 引擎版本 | {fp.get('engine_version') or '—'} |\n"
        f"| 品类 | {ctx.get('genre')} |\n"
        f"| 保护 | {prot} |\n"
        f"| 热更 | {hot} |\n"
        f"| 输入完整度 | {ctx.get('input_score')}/100 |\n\n"
        f"## 循环\n\n"
        f"- 局内：{chain('session')}\n"
        f"- 日：{chain('day')}\n"
        f"- 长线：{chain('meta')}\n\n"
        f"图源：`../diagrams/*.mmd`。IR：`../data/game.ir.json`。\n"
    )


def _levels_readme(ir: dict, ctx: dict) -> str:
    levels = ir.get("levels") or []
    grades: dict[str, int] = {}
    for lv in levels:
        g = str(lv.get("rebuild_grade") or "L?")
        grades[g] = grades.get(g, 0) + 1
    grade_s = ", ".join(f"{k}×{v}" for k, v in sorted(grades.items())) or "无"
    chapters = ctx.get("n_chapters")
    extra = f"（约 {chapters} 章）" if chapters else ""
    return (
        f"# 关卡\n\n"
        f"共 {len(levels)} 关{extra}。重建等级：{grade_s}。\n\n"
        f"- 策划正文：[README.md](README.md)（按章 markdown，不是空 JSON）\n"
        f"- 索引：[`../../data/levels/index.csv`](../../data/levels/index.csv)\n\n"
        f"L0 = 只有 ID；几何在 bundle 里未解码。不要把空 JSON 当关卡稿。\n"
    )


def _data_readme() -> str:
    return (
        "# data/\n\n"
        "| 文件 | 用途 |\n"
        "|---|---|\n"
        "| `game.ir.json` | 全量 GameIR，写代码时的单一事实源 |\n"
        "| `claims.json` | 带 evidence 的主张 |\n"
        "| `radar.json` | 20 维完整度 |\n"
        "| `levels/index.csv` | 关卡索引（策划正文在 `策划/关卡/`） |\n"
        "| `tables/` | CSV |\n"
        "| `specs/` | 给代码生成的小规格 |\n"
        "| `configs/` | 从包里抽出的配置 |\n"
        "| `scripts/` | 脚本（无 so/dll） |\n"
        "\n"
        "和 `策划/gdd/` 冲突时，以本目录和 `claims.json` 为准。\n"
    )


def _copy_if(src: Path, dst: Path) -> None:
    if src.exists() and src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _place(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            dst.unlink()
        except OSError:
            pass
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
