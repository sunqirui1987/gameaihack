from __future__ import annotations

import re


def guess_genre(ir: dict) -> dict:
    scores: dict[str, float] = {}
    levels = ir.get("levels") or []
    tables = ir.get("tables") or []
    pkg = ((ir.get("package") or {}).get("name") or "").lower()
    names = " ".join(
        [
            pkg,
            *(t.get("id", "") + " " + t.get("role", "") for t in tables),
            *(str(lv.get("kind", "")) + " " + str(lv.get("id", "")) for lv in levels[:30]),
            *(r.get("name", "") for r in (ir.get("resources") or [])[:80]),
            *(str((lv.get("extra") or {}).get("chapter", "")) for lv in levels[:5]),
        ]
    ).lower()
    kinds = [lv.get("kind") for lv in levels]
    if kinds.count("puzzle_board") >= 1:
        scores["puzzle"] = 0.8
    if any(t.get("role") == "enemy" for t in tables):
        scores["rpg"] = scores.get("rpg", 0) + 0.4
    if re.search(r"(?<![a-z])merge(?![a-z])", names) or "合成" in names:
        scores["merge"] = 0.75
    if kinds.count("wave_spawner") >= 1 or re.search(r"(?<![a-z])tower(?![a-z])", names):
        scores["td"] = 0.7
    if "runner" in names or kinds.count("runner_segment"):
        scores["runner"] = 0.7
    if any(t.get("role") == "gacha" for t in tables):
        scores["gacha"] = 0.5
    if "slingshot" in names or "弹弓" in names:
        scores["slingshot"] = 0.85
    if not scores:
        engine = (ir.get("fingerprint") or {}).get("engine")
        return {"id": None, "confidence": 0, "engine": engine}
    gid = max(scores, key=scores.get)
    return {"id": gid, "confidence": round(min(0.99, scores[gid]), 2)}
