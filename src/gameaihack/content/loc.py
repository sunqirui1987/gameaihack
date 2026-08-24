from __future__ import annotations

import json
from pathlib import Path


def extract_loc(norm: Path, merged: Path, tables: list[dict]) -> dict:
    languages: list[str] = []
    samples: list[dict] = []
    for t in tables:
        if t.get("role") == "dialogue":
            for row in t.get("preview_rows") or []:
                for k, v in row.items():
                    if isinstance(v, str) and len(v) >= 2:
                        samples.append({"key": str(row.get("id") or k), "text": v[:80]})
                        if len(samples) >= 30:
                            break
    for root in (norm, merged):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            name = p.name.lower()
            if not any(x in name or x in p.as_posix().lower() for x in ("loc", "i18n", "lang", "string", "zh", "en")):
                continue
            if p.suffix.lower() not in {".json", ".txt", ".xml"}:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, json.JSONDecodeError):
                continue
            pairs = _flatten(data)
            if len(pairs) < 3:
                continue
            for k, v in pairs[:20]:
                samples.append({"key": k, "text": v[:80], "path": p.name})
            if "zh" in name:
                languages.append("zh")
            if "en" in name:
                languages.append("en")
            if len(samples) >= 40:
                break
    languages = sorted(set(languages)) or (["und"] if samples else [])
    return {"languages": languages, "samples": samples[:40]}


def _flatten(data, prefix="") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(data, dict):
        if all(isinstance(v, str) for v in data.values()) and data:
            return [(str(k), v) for k, v in list(data.items())[:80]]
        for k, v in data.items():
            out.extend(_flatten(v, f"{prefix}{k}."))
    elif isinstance(data, list):
        for i, v in enumerate(data[:50]):
            out.extend(_flatten(v, f"{prefix}{i}."))
    elif isinstance(data, str) and prefix:
        out.append((prefix.rstrip("."), data))
    return out
