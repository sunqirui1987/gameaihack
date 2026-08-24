from __future__ import annotations

from pathlib import Path

from gameaihack.extract.base import ExtractReport
from gameaihack.extract.cocos import extract_cocos
from gameaihack.extract.loose import extract_loose
from gameaihack.extract.other import extract_godot, extract_unreal
from gameaihack.extract.unity import extract_unity

MODE_CAP = {"brief": 80, "standard": 2500, "deep": 8000}


def run_extract(
    merged: Path,
    dest: Path,
    fingerprint: dict,
    *,
    mode: str = "standard",
    adapters: dict | None = None,
) -> ExtractReport:
    cap = MODE_CAP.get(mode, 2500)
    adapters = adapters or {}
    engine = (fingerprint or {}).get("engine") or "unknown"
    reports: list[ExtractReport] = []

    reports.append(extract_loose(merged, dest, max_files=cap))
    data_dir = merged / "assets" / "bin" / "Data"
    has_unity = engine == "unity" or data_dir.exists()
    if adapters.get("unity", True) and has_unity:
        reports.append(extract_unity(merged, dest, max_files=cap))
    has_lua = False
    if engine in {"cocos", "unknown"}:
        has_lua = next(merged.rglob("*.lua"), None) is not None or next(merged.rglob("*.jsc"), None) is not None
    if adapters.get("cocos", True) and (engine == "cocos" or has_lua):
        reports.append(extract_cocos(merged, dest))
    if adapters.get("unreal", True) and (
        engine == "unreal" or next(merged.rglob("*.pak"), None) is not None
    ):
        reports.append(extract_unreal(merged, dest))
    if adapters.get("godot", True) and (
        engine == "godot" or next(merged.rglob("*.pck"), None) is not None
    ):
        reports.append(extract_godot(merged, dest))

    merged_report = ExtractReport(adapter="all")
    seen: set[str] = set()
    for r in reports:
        merged_report.discovered += r.discovered
        merged_report.encrypted += r.encrypted
        merged_report.warnings.extend(f"{r.adapter}:{w}" for w in r.warnings)
        merged_report.extra[r.adapter] = r.extra
        for it in r.items:
            if it.sha256 in seen:
                continue
            seen.add(it.sha256)
            merged_report.items.append(it)
    return merged_report
