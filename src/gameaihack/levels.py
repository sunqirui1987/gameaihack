from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from gameaihack.pngutil import render_board_png
from gameaihack.unity_index import index_unity_levels


def rebuild_levels(
    merged: Path,
    norm: Path,
    tables: list[dict],
    preview_dir: Path,
) -> list[dict]:
    levels: list[dict] = []
    seen: set[str] = set()

    for path in _iter_json(merged, norm):
        lv = _from_json_file(path, preview_dir)
        if lv and lv["id"] not in seen:
            seen.add(lv["id"])
            levels.append(lv)

    for path in list(merged.rglob("*.tmx")) + list(norm.rglob("*.tmx")):
        lv = _from_tmx(path, preview_dir)
        if lv and lv["id"] not in seen:
            seen.add(lv["id"])
            levels.append(lv)

    for t in tables:
        if t.get("role") != "level":
            continue
        for i, row in enumerate(t.get("preview_rows") or []):
            lid = str(row.get("id") or row.get("stage") or row.get("stageId") or f"{t['id']}_{i}")
            if lid in seen:
                continue
            seen.add(lid)
            levels.append(
                {
                    "id": lid,
                    "index": _index_of(lid, i),
                    "name": str(row.get("name") or row.get("title") or lid),
                    "kind": "unknown",
                    "rebuild_grade": "L0",
                    "unlock": {"requires": [str(row["pre_id"])] if row.get("pre_id") else [], "stars": int(row.get("stars") or 0) if _intish(row.get("stars")) else 0},
                    "win": [],
                    "lose": [],
                    "stars": [],
                    "layers": [],
                    "entities": [],
                    "triggers": [],
                    "waves": [],
                    "preview": None,
                    "teaching": [],
                    "evidence": t.get("evidence") or [],
                }
            )

    for lv in index_unity_levels(merged):
        if lv["id"] not in seen:
            seen.add(lv["id"])
            levels.append(lv)

    levels.sort(key=lambda x: (x.get("index") or 0, str(x.get("id"))))
    _mark_teaching(levels)
    return levels


def _iter_json(*roots: Path):
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.json"):
            name = p.name.lower()
            rel = p.as_posix().lower()
            if "/res/" in rel or "/androidx" in rel:
                continue
            if any(k in rel for k in ("level", "stage", "map", "board", "puzzle")):
                yield p
            elif name.startswith("lv") or re.match(r"stage_?\d+", name):
                yield p


def _from_json_file(path: Path, preview_dir: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return None
    board = _find_board(data)
    lid = str(
        (data.get("id") if isinstance(data, dict) else None)
        or path.stem
    )
    if board:
        preview = preview_dir / f"{_safe(lid)}.png"
        render_board_png(preview, board)
        win, lose = _win_lose(data if isinstance(data, dict) else {})
        grade = "L3" if win or lose or (isinstance(data, dict) and data.get("moves")) else "L2"
        entities = _entities_from_board(board)
        return _level(
            lid,
            path,
            kind="puzzle_board",
            grade=grade,
            board=board,
            win=win,
            lose=lose,
            entities=entities,
            preview=preview.name,
            extra=data if isinstance(data, dict) else {},
        )
    if isinstance(data, dict) and any(k in data for k in ("waves", "spawns", "spawn")):
        waves = data.get("waves") or data.get("spawns") or []
        if not isinstance(waves, list):
            waves = [waves]
        return _level(
            lid,
            path,
            kind="wave_spawner",
            grade="L3" if waves else "L1",
            waves=waves if isinstance(waves, list) else [],
            extra=data,
        )
    if isinstance(data, dict) and any(k in data for k in ("entities", "actors", "objects")):
        ents = data.get("entities") or data.get("actors") or data.get("objects") or []
        return _level(
            lid,
            path,
            kind="scene_graph_3d",
            grade="L2" if ents else "L1",
            entities=ents if isinstance(ents, list) else [],
            extra=data,
        )
    return None


def _from_tmx(path: Path, preview_dir: Path) -> dict | None:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    w = int(root.attrib.get("width") or 0)
    h = int(root.attrib.get("height") or 0)
    board: list[list] = []
    for layer in root.findall("layer"):
        data_el = layer.find("data")
        if data_el is None or not (data_el.text or "").strip():
            continue
        encoding = (data_el.attrib.get("encoding") or "").lower()
        raw = data_el.text.strip()
        nums: list[int] = []
        if encoding == "csv" or "," in raw:
            nums = [int(x) for x in re.findall(r"-?\d+", raw)]
        if nums and w:
            for y in range(h):
                board.append(nums[y * w : (y + 1) * w])
            break
    lid = path.stem
    preview_name = None
    if board:
        preview = preview_dir / f"{_safe(lid)}.png"
        render_board_png(preview, board)
        preview_name = preview.name
    return _level(
        lid,
        path,
        kind="tilemap_2d",
        grade="L2" if board else "L1",
        board=board,
        preview=preview_name,
        extra={"w": w, "h": h},
    )


def _find_board(data) -> list[list] | None:
    if isinstance(data, list) and data and all(isinstance(r, list) for r in data):
        return data
    if not isinstance(data, dict):
        return None
    for key in ("board", "map", "grid", "tiles", "cells"):
        val = data.get(key)
        if isinstance(val, list) and val and all(isinstance(r, list) for r in val):
            return val
        if isinstance(val, list) and val and all(not isinstance(x, list) for x in val) and data.get("width"):
            w = int(data["width"])
            return [val[i : i + w] for i in range(0, len(val), w)]
    return None


def _win_lose(data: dict) -> tuple[list, list]:
    win, lose = [], []
    if not isinstance(data, dict):
        return win, lose
    if data.get("moves") or data.get("maxMoves"):
        win.append({"type": "clear_board"})
        lose.append({"type": "moves_out", "moves": data.get("moves") or data.get("maxMoves")})
    if data.get("win"):
        win.append({"type": str(data["win"])})
    if data.get("lose"):
        lose.append({"type": str(data["lose"])})
    if data.get("time") or data.get("limit"):
        lose.append({"type": "timeout"})
    return win, lose


def _entities_from_board(board: list[list]) -> list[dict]:
    counts: dict[str, int] = {}
    for y, row in enumerate(board):
        for x, val in enumerate(row):
            if val in (0, None, "", "."):
                continue
            key = str(val)
            counts[key] = counts.get(key, 0) + 1
    return [{"template": k, "count": n, "x": 0, "y": 0} for k, n in sorted(counts.items())]


def _level(lid, path: Path, *, kind, grade, board=None, win=None, lose=None, entities=None, waves=None, preview=None, extra=None):
    size = None
    layers = []
    if board:
        size = {"w": max(len(r) for r in board), "h": len(board), "unit": "tile"}
        layers = [{"name": "board", "tiles": "inline"}]
    return {
        "id": str(lid),
        "index": _index_of(str(lid), 0),
        "name": str(lid),
        "kind": kind,
        "rebuild_grade": grade,
        "size": size,
        "unlock": {"requires": [], "stars": 0},
        "win": win or [],
        "lose": lose or [],
        "stars": [],
        "layers": layers,
        "entities": entities or [],
        "triggers": [],
        "waves": waves or [],
        "preview": preview,
        "teaching": [],
        "evidence": [{"path": path.name, "extractor": "levels", "locator": str(path)}],
        "extra": {k: extra[k] for k in list(extra or {}) if k not in {"board", "map", "grid", "tiles"}} if extra else {},
    }


def _index_of(lid: str, default: int) -> int:
    m = re.search(r"(\d+)", lid)
    return int(m.group(1)) if m else default


def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name)[:80] or "level"


def _intish(v) -> bool:
    try:
        int(v)
        return True
    except (TypeError, ValueError):
        return False


def _mark_teaching(levels: list[dict]) -> None:
    seen_templates: set[str] = set()
    for lv in levels:
        templates = {str(e.get("template")) for e in lv.get("entities") or [] if e.get("template")}
        new = sorted(templates - seen_templates)
        lv["teaching"] = new
        seen_templates |= templates
