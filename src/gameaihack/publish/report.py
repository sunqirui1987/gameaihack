from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from gameaihack import __version__
from gameaihack.content.design import render_gdd_chapters
from gameaihack.core.job import slugify
from gameaihack.core.layout import extract_dir, raw_dir
from gameaihack.core.paths import templates_dir
from gameaihack.publish.projects import write_ai_projects


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(templates_dir())),
        autoescape=select_autoescape(["html"]),
        keep_trailing_newline=True,
    )


def one_liner(ir: dict) -> str:
    pkg = ir["package"]["name"]
    fp = ir["fingerprint"]
    engine = fp.get("engine") or "unknown"
    backend = fp.get("script_backend") or "n/a"
    genre = (ir.get("genre_guess") or {}).get("id")
    n_res = len(ir.get("resources") or [])
    n_lv = len(ir.get("levels") or [])
    n_tb = len(ir.get("tables") or [])
    bit = f"{pkg} · 引擎 {engine}（{backend}）"
    if genre:
        bit += f" · 品类 {genre}"
    bit += f" · 资源 {n_res} · 表 {n_tb} · 关卡 {n_lv}"
    return bit


def render_deliverable(
    job_dir: Path,
    ir: dict,
    extra_warnings: list[str] | None = None,
    thumbs_only: bool = True,
    overwrite_design: bool = True,
) -> None:
    dest = raw_dir(job_dir) / "deliverable"
    dest.mkdir(parents=True, exist_ok=True)
    env = _env()
    fp = ir["fingerprint"]
    score = ir["input_profile"]["score"]
    warnings = list(ir["input_profile"].get("warnings") or [])
    if extra_warnings:
        warnings.extend(extra_warnings)
    incomplete = score < 60
    radar_avg = 0.0
    if ir.get("radar"):
        radar_avg = sum(r["score"] for r in ir["radar"]) / len(ir["radar"])
    ctx = {
        "tool_version": __version__,
        "job_id": ir["job_id"],
        "package_name": ir["package"]["name"],
        "version_name": ir["package"].get("version_name") or "—",
        "version_code": ir["package"].get("version_code") or "—",
        "engine": fp.get("engine"),
        "script_backend": fp.get("script_backend") or "—",
        "engine_version": fp.get("engine_version") or "—",
        "protection": ", ".join(fp.get("protection") or []) or "none",
        "hotupdate": ", ".join(fp.get("hotupdate") or []) or "none",
        "matched_rules": ", ".join(fp.get("matched_rules") or []) or "—",
        "input_score": score,
        "warnings": warnings,
        "incomplete": incomplete,
        "radar": ir.get("radar") or [],
        "radar_avg": round(radar_avg, 2),
        "one_liner": one_liner(ir),
        "sha256": ir["package"].get("sha256") or "—",
        "mode": (ir.get("coverage") or {}).get("mode") or "standard",
        "genre": (ir.get("genre_guess") or {}).get("id") or "未判定",
        "resources": ir.get("resources") or [],
        "levels": ir.get("levels") or [],
        "tables": ir.get("tables") or [],
        "claims": ir.get("claims") or [],
        "loops": ir.get("loops") or {},
        "simulations": ir.get("simulations") or [],
        "coverage": ir.get("coverage") or {},
        "n_res": len(ir.get("resources") or []),
        "n_lv": len(ir.get("levels") or []),
        "n_tb": len(ir.get("tables") or []),
        "n_claim": len(ir.get("claims") or []),
        "resource_cards": [],
        "n_chapters": len({(lv.get("extra") or {}).get("chapter") for lv in (ir.get("levels") or []) if (lv.get("extra") or {}).get("chapter") is not None}),
        "level_sample": "、".join(lv.get("id", "") for lv in (ir.get("levels") or [])[:8]) or "—",
    }

    (dest / "COVER.md").write_text(env.get_template("cover.md.j2").render(**ctx), encoding="utf-8")
    (dest / "README.md").write_text(env.get_template("readme.md.j2").render(**ctx), encoding="utf-8")
    (dest / "LEGAL.txt").write_text(env.get_template("legal.txt.j2").render(**ctx), encoding="utf-8")
    (dest / "OPEN.txt").write_text(
        "若 index.html 在 file:// 下脚本受限，在本目录执行：\npython -m http.server 8765\n然后打开 http://127.0.0.1:8765/\n",
        encoding="utf-8",
    )

    catalog = _copy_assets(job_dir, dest, ir, thumbs_only=thumbs_only)
    ctx["resource_cards"] = [c for c in catalog if c.get("thumb")][:120] or catalog[:80]
    _write_tables(dest, ir)
    _write_levels(job_dir, dest, ir)
    _write_design(dest, ir, warnings, incomplete)
    _write_diagrams(job_dir, dest, ir)
    _write_feel(dest, ir)

    html = env.get_template("index.html.j2").render(**ctx)
    # gallery uses copied previews; regenerate after files exist
    (dest / "index.html").write_text(html, encoding="utf-8")
    report = job_dir / "report"
    report.mkdir(parents=True, exist_ok=True)
    (report / "index.html").write_text(html, encoding="utf-8")

    (dest / "coverage.json").write_text(
        json.dumps(ir.get("coverage") or {}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (dest / "input_profile.json").write_text(
        json.dumps(ir["input_profile"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    machine = dest / "machine"
    machine.mkdir(exist_ok=True)
    (machine / "game.ir.json").write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (machine / "coverage.json").write_text((dest / "coverage.json").read_text(encoding="utf-8"), encoding="utf-8")
    (machine / "claims.json").write_text(json.dumps(ir.get("claims") or [], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_src = job_dir / "run_manifest.json"
    if manifest_src.exists():
        (machine / "run_manifest.json").write_text(manifest_src.read_text(encoding="utf-8"), encoding="utf-8")
    write_ai_projects(job_dir, ir, ctx, overwrite_design=overwrite_design)
    _ = slugify


def _copy_assets(job_dir: Path, dest: Path, ir: dict, *, thumbs_only: bool) -> list[dict]:
    thumbs = dest / "assets" / "thumbs"
    full = dest / "assets" / "full"
    thumbs.mkdir(parents=True, exist_ok=True)
    catalog = []
    norm = extract_dir(job_dir) / "normalized"
    n = 0
    for res in ir.get("resources") or []:
        src = norm / (res.get("export_path") or "")
        entry = {
            "id": res.get("id"),
            "name": res.get("name"),
            "kind": res.get("kind"),
            "original_path": res.get("original_path"),
            "thumb": None,
            "full": None,
        }
        if src.exists() and src.is_file():
            n += 1
            if n > 400 and thumbs_only:
                catalog.append(entry)
                continue
            suffix = src.suffix.lower() or ".bin"
            tname = f"{res.get('id')}{suffix}"
            if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"} or res.get("kind") in {"texture", "sprite"}:
                target = thumbs / tname
                try:
                    shutil.copy2(src, target)
                    entry["thumb"] = f"assets/thumbs/{tname}"
                except OSError:
                    pass
            if not thumbs_only:
                full.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src, full / tname)
                    entry["full"] = f"assets/full/{tname}"
                except OSError:
                    pass
        catalog.append(entry)
    (dest / "assets" / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return catalog


def _write_tables(dest: Path, ir: dict) -> None:
    tdir = dest / "tables"
    tdir.mkdir(exist_ok=True)
    idx = tdir / "index.csv"
    with idx.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "role", "rows", "schema_state", "source"])
        for t in ir.get("tables") or []:
            w.writerow([t.get("id"), t.get("role"), t.get("row_count"), t.get("schema_state"), t.get("path")])
            cols = [c["name"] for c in t.get("columns") or []]
            if not cols:
                continue
            outp = tdir / f"{t['id'].replace(':', '_')}.csv"
            with outp.open("w", encoding="utf-8-sig", newline="") as tf:
                dw = csv.DictWriter(tf, fieldnames=cols, extrasaction="ignore")
                dw.writeheader()
                for row in t.get("preview_rows") or []:
                    dw.writerow({c: row.get(c, "") for c in cols})


def _write_levels(job_dir: Path, dest: Path, ir: dict) -> None:
    ldir = dest / "levels"
    ldir.mkdir(exist_ok=True)
    preview_src = extract_dir(job_dir) / "normalized/maps/previews"
    items = []
    all_levels = ir.get("levels") or []
    (ldir / "all.json").write_text(json.dumps(all_levels, ensure_ascii=False) + "\n", encoding="utf-8")
    for i, lv in enumerate(all_levels):
        if i >= 80:
            items.append({"id": lv["id"], "grade": lv.get("rebuild_grade"), "kind": lv.get("kind"), "preview": None})
            continue
        sub = ldir / str(lv["id"])
        sub.mkdir(exist_ok=True)
        (sub / "level.json").write_text(json.dumps(lv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        prev = lv.get("preview")
        if prev:
            src = preview_src / prev
            if src.exists():
                shutil.copy2(src, sub / "preview.png")
                lv_out_prev = f"levels/{lv['id']}/preview.png"
            else:
                lv_out_prev = None
        else:
            lv_out_prev = None
        items.append(
            {
                "id": lv["id"],
                "grade": lv.get("rebuild_grade"),
                "kind": lv.get("kind"),
                "preview": lv_out_prev,
            }
        )
    (ldir / "index.json").write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gallery = ["# 关卡画廊\n"]
    for it in items:
        gallery.append(f"## {it['id']} · {it.get('grade')} · {it.get('kind')}\n")
        if it.get("preview"):
            gallery.append(f"![{it['id']}]({it['preview']})\n")
    (ldir / "gallery.md").write_text("\n".join(gallery), encoding="utf-8")
    cards = []
    for it in items:
        img = f'<img src="{it["preview"]}" alt="{it["id"]}"/>' if it.get("preview") else ""
        cards.append(f'<figure><a href="levels/{it["id"]}/level.json">{img}<figcaption>{it["id"]} · {it.get("grade")}</figcaption></a></figure>')
    (ldir / "gallery.html").write_text(
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'/><title>关卡画廊</title>"
        "<style>body{font-family:sans-serif;background:#0f1419;color:#e7ecf3}main{max-width:1100px;margin:auto;padding:24px}"
        ".g{display:flex;flex-wrap:wrap;gap:12px}img{width:180px;border-radius:8px}a{color:#7dd3fc;text-decoration:none}</style>"
        "</head><body><main><h1>关卡画廊</h1><div class='g'>"
        + "".join(cards)
        + "</div></main></body></html>\n",
        encoding="utf-8",
    )


def _write_design(dest: Path, ir: dict, warnings: list[str], incomplete: bool) -> None:
    design = dest / "design"
    design.mkdir(exist_ok=True)
    (design / "claims.json").write_text(json.dumps(ir.get("claims") or [], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 雷达与缺口\n", f"{one_liner(ir)}\n", "| 维 | 分 | 证据 | 缺口 |", "|---|---|---|---|"]
    for r in ir.get("radar") or []:
        blockers = ", ".join(r.get("blockers") or []) or "—"
        lines.append(f"| {r.get('label', r['dimension'])} | {r['score']}/{r['max']} | {r.get('evidence_count', 0)} | {blockers} |")
    (design / "00-雷达与缺口.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    chapters = render_gdd_chapters(ir)
    for fn, body in chapters.items():
        (design / fn).write_text(body, encoding="utf-8")
    unk = ["# 未知项\n"]
    if incomplete:
        unk.append("本报告基于**残缺输入**。补 OBB / 热更缓存后再跑。\n")
    if warnings:
        unk.append("## 输入警告\n")
        for w in warnings:
            unk.append(f"- `{w}`")
        unk.append("")
    extras = [u for u in (ir.get("unknowns") or []) if u not in warnings]
    if extras:
        unk.append("## 抽取警告\n")
        for u in extras[:80]:
            unk.append(f"- {u}")
        unk.append("")
    if not warnings and not extras:
        unk.append("无额外未知项。雷达 0 分的维仍代表未还原，不是「游戏没有该系统」。\n")
    (design / "09-未知项.md").write_text("\n".join(unk), encoding="utf-8")


def _write_diagrams(job_dir: Path, dest: Path, ir: dict) -> None:
    ddir = dest / "diagrams"
    ddir.mkdir(exist_ok=True)
    src = extract_dir(job_dir) / "normalized/diagrams"
    if src.exists():
        for p in src.glob("*"):
            shutil.copy2(p, ddir / p.name)
    (ddir / "progression.mmd").write_text(_progress_mmd(ir), encoding="utf-8")


def _progress_mmd(ir: dict) -> str:
    levels = ir.get("levels") or []
    if not levels:
        return "%% progression empty\n"
    lines = ["flowchart TD"]
    prev = None
    for lv in levels[:80]:
        nid = str(lv["id"]).replace("-", "_")
        lines.append(f"  {nid}[{lv['id']}]")
        if prev:
            lines.append(f"  {prev} --> {nid}")
        prev = nid
    return "\n".join(lines) + "\n"


def _write_feel(dest: Path, ir: dict) -> None:
    feel = dest / "feel"
    feel.mkdir(exist_ok=True)
    juice = ir.get("feel", {}).get("juice") or []
    inp = ir.get("feel", {}).get("input") or []
    cam = ir.get("feel", {}).get("camera") or []
    lines = ["# 手感清单\n"]
    if not (juice or inp or cam):
        lines.append("未从脚本中还原 coyote / shake / 缓冲等字段。\n")
    else:
        if juice:
            lines.append("## Juice\n")
            for j in juice:
                lines.append(f"- {j.get('id') if isinstance(j, dict) else j}")
        if inp:
            lines.append("\n## Input\n")
            for j in inp:
                lines.append(f"- {j}")
        if cam:
            lines.append("\n## Camera\n")
            for j in cam:
                lines.append(f"- {j}")
        lines.append("")
    (feel / "inventory.md").write_text("\n".join(lines), encoding="utf-8")
