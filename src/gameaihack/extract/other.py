from __future__ import annotations

import zipfile
from pathlib import Path

from gameaihack.core.fs import iter_files
from gameaihack.extract.base import KIND_DIR, ExtractItem, ExtractReport, sha256_path


def extract_unreal(merged: Path, dest: Path) -> ExtractReport:
    report = ExtractReport(adapter="unreal")
    paks = [p for p in iter_files(merged) if p.suffix.lower() in {".pak", ".ucas"}]
    report.discovered = len(paks)
    dest.mkdir(parents=True, exist_ok=True)
    listing = dest / "misc" / "unreal_paks.txt"
    listing.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for pak in paks:
        rel = pak.relative_to(merged).as_posix()
        lines.append(f"{rel}\t{pak.stat().st_size}")
        if zipfile.is_zipfile(pak):
            with zipfile.ZipFile(pak) as zf:
                for n in zf.namelist()[:500]:
                    lines.append(f"  {n}")
        report.items.append(
            ExtractItem(
                kind="other",
                name=pak.name,
                original_path=rel,
                export_rel=listing.relative_to(dest).as_posix(),
                sha256=sha256_path(pak, limit=8 * 1024 * 1024),
                bytes=pak.stat().st_size,
                extractor="unreal",
                meta={"container": "pak"},
            )
        )
    if lines:
        listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif paks:
        report.warnings.append("pak_unreadable")
    return report


def extract_godot(merged: Path, dest: Path) -> ExtractReport:
    report = ExtractReport(adapter="godot")
    dest.mkdir(parents=True, exist_ok=True)
    pcks = [p for p in iter_files(merged) if p.suffix.lower() == ".pck"]
    report.discovered = len(pcks)
    for pck in pcks:
        rel = pak_rel = pck.relative_to(merged).as_posix()
        magic = pck.read_bytes()[:4]
        report.extra.setdefault("pck", []).append(
            {"path": rel, "magic": magic.decode("latin1", "replace")}
        )
        if magic != b"GDPC":
            report.warnings.append(f"pck_magic:{rel}")
    # .tscn / .gd already handled by loose copier
    return report
