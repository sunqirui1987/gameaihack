from __future__ import annotations

import re

VERB_PAT = re.compile(
    r"\b(jump|shoot|merge|swipe|tap|build|craft|spin|draw|dash|dodge|reload|upgrade|gacha|summon|attack|skill)\b",
    re.I,
)


def extract_verbs(blob: str, tables: list[dict], genre: str | None) -> list[dict]:
    found: dict[str, str] = {}
    for m in VERB_PAT.finditer(blob or ""):
        v = m.group(1).lower()
        found.setdefault(v, "script")
    if any(t.get("role") == "skill" for t in tables):
        found.setdefault("skill", "table")
    if genre == "puzzle":
        found.setdefault("match", "genre")
    if genre == "merge":
        found.setdefault("merge", "genre")
    if genre == "td":
        found.setdefault("build", "genre")
    return [{"id": k, "source": src} for k, src in sorted(found.items())]
