from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROLE_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("iap", ("sku", "productid", "product_id", "inapp", "rmb", "usd", "iap")),
    ("gacha", ("gacha", "wish", "recruit", "pity", "banner")),
    ("shop", ("price", "cost", "shop", "store", "buy")),
    ("enemy", ("hp", "atk", "attack", "defense", "monster", "enemy", "mob")),
    ("skill", ("skill", "cooldown", "cd", "damage", "buff")),
    ("drop", ("drop", "loot", "weight", "rate", "prob")),
    ("level", ("stage", "levelid", "level_id", "wave", "mapid", "pre_id", "unlock")),
    ("item", ("item", "prop", "equip", "weapon")),
    ("economy_const", ("stamina", "energy", "gold", "diamond", "gem", "coin")),
    ("dialogue", ("dialogue", "talk", "story", "line")),
    ("quest", ("quest", "task", "mission")),
    ("spawn_wave", ("wave", "spawn", "interval")),
]


def discover_tables(norm: Path, merged: Path, preview_rows: int = 20) -> list[dict]:
    from gameaihack.core.fs import iter_files

    table_suf = {".json", ".csv", ".txt", ".xml"}
    files: list[Path] = []
    if norm.exists():
        norm_files = [p for p in iter_files(norm) if p.suffix.lower() in table_suf]
        if any(p.suffix.lower() == ".json" for p in norm_files):
            files = norm_files
    if not files:
        seen_p: set[Path] = set()
        for root in (p for p in (norm, merged) if p.exists()):
            for p in iter_files(root):
                if p.suffix.lower() in table_suf and p not in seen_p:
                    seen_p.add(p)
                    files.append(p)
    tables = []
    seen: set[str] = set()
    idx = 0
    for path in files:
        try:
            rel = path.relative_to(norm).as_posix() if norm in path.parents or path == norm else path.name
        except ValueError:
            rel = path.name
        rel_l = str(path).replace("\\", "/").lower()
        if any(
            s in rel_l
            for s in (
                "/res/",
                "mbridge",
                "applovin",
                "androidx",
                "google/protobuf",
                "kotlin",
                "consent_flow",
            )
        ):
            continue
        if path.suffix.lower() == ".txt" and path.stat().st_size > 2_000_000:
            continue
        if path.name.lower() in {"runtimeinitializeonloads.json", "scriptingassemblies.json", "google-services-desktop.json"}:
            continue
        parsed = _parse_file(path)
        if not parsed:
            continue
        columns, rows = parsed
        if len(columns) < 2 or len(rows) < 1:
            continue
        sig = f"{tuple(columns)}:{len(rows)}"
        if sig in seen:
            continue
        seen.add(sig)
        role, schema_state = tag_role(path.name, columns, rows)
        idx += 1
        preview = rows[:preview_rows]
        tables.append(
            {
                "id": f"table:{_slug(path.stem)}_{idx:03d}",
                "role": role,
                "schema_state": schema_state,
                "columns": [{"name": c, "type": _col_type(rows, c), "semantic": _semantic(c)} for c in columns],
                "row_count": len(rows),
                "path": rel,
                "abs_path": str(path),
                "preview_rows": preview,
                "evidence": [{"path": rel, "extractor": "tables", "locator": path.name}],
            }
        )
    return tables


def tag_role(filename: str, columns: list[str], rows: list[dict]) -> tuple[str, str]:
    blob = " ".join([filename.lower(), *[c.lower() for c in columns]])
    for role, hints in ROLE_HINTS:
        if any(h in blob for h in hints):
            return role, "exact"
    return "other", "inferred"


def _semantic(col: str) -> str:
    c = col.lower()
    if c in {"id", "sid", "tid"}:
        return "primary_key"
    if c in {"hp", "atk", "def", "attack", "defense"}:
        return f"stat.{c}"
    if c in {"price", "cost", "gold", "diamond"}:
        return "economy"
    if "stage" in c or c in {"pre_id", "unlock"}:
        return "progress"
    return ""


def _col_type(rows: list[dict], col: str) -> str:
    vals = [r.get(col) for r in rows[:15] if r.get(col) not in (None, "")]
    if not vals:
        return "string"
    if all(_is_int(v) for v in vals):
        return "int"
    if all(_is_float(v) for v in vals):
        return "float"
    return "string"


def _is_int(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return bool(re.fullmatch(r"-?\d+", str(v)))


def _is_float(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "t"


def _parse_file(path: Path) -> tuple[list[str], list[dict]] | None:
    suf = path.suffix.lower()
    try:
        if suf == ".csv":
            with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
                reader = csv.DictReader(f)
                cols = list(reader.fieldnames or [])
                rows = [dict(r) for r in reader]
                return cols, rows
        text = path.read_text(encoding="utf-8", errors="ignore")
        text = text.strip()
        if not text:
            return None
        if suf in {".json", ".txt"} and text[:1] in "{[":
            data = json.loads(text)
            return _from_json(data)
        if suf == ".xml":
            return _from_xml(text)
    except (OSError, json.JSONDecodeError, csv.Error, UnicodeDecodeError):
        return None
    return None


def _from_xml(text: str) -> tuple[list[str], list[dict]] | None:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    rows = []
    children = list(root)
    if not children:
        return None
    tag = children[0].tag
    items = root.findall(tag)
    if len(items) < 2:
        items = [el for el in root.iter() if list(el.attrib)]
    for el in items[:500]:
        row = dict(el.attrib)
        if el.text and el.text.strip():
            row["_text"] = el.text.strip()
        for ch in list(el):
            if ch.text and ch.text.strip() and ch.tag not in row:
                row[ch.tag] = ch.text.strip()
        if len(row) >= 2:
            rows.append(row)
    if len(rows) < 2:
        return None
    cols = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    return cols, rows


def _from_json(data) -> tuple[list[str], list[dict]] | None:
    if isinstance(data, dict):
        for key in ("data", "list", "items", "rows", "table"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            if all(isinstance(v, dict) for v in data.values()) and data:
                rows = []
                for k, v in data.items():
                    row = dict(v)
                    row.setdefault("id", k)
                    rows.append(row)
                cols = sorted({c for r in rows for c in r.keys()})
                return cols, rows
            return None
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        cols = []
        seen = set()
        for r in data:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    cols.append(str(k))
        rows = [{str(k): v for k, v in r.items()} for r in data]
        return cols, rows
    return None
