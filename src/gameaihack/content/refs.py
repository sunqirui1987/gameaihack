from __future__ import annotations


def link_references(ir: dict) -> None:
    resources = ir.get("resources") or []
    by_name = {}
    for r in resources:
        by_name.setdefault(r.get("name", "").lower(), []).append(r)
        stem = (r.get("original_path") or "").lower()
        by_name.setdefault(stem, []).append(r)

    def mark(key: str, ref: str) -> None:
        if not key:
            return
        k = str(key).lower()
        for r in resources:
            if k in (r.get("name") or "").lower() or k in (r.get("original_path") or "").lower():
                refs = r.setdefault("referenced_by", [])
                if ref not in refs:
                    refs.append(ref)

    for lv in ir.get("levels") or []:
        lid = f"level:{lv.get('id')}"
        for e in lv.get("entities") or []:
            mark(str(e.get("template") or ""), lid)
        mark(str(lv.get("id") or ""), lid)
    for t in ir.get("tables") or []:
        tid = t.get("id")
        for row in t.get("preview_rows") or []:
            for val in row.values():
                if isinstance(val, str) and 2 <= len(val) <= 40:
                    mark(val, tid)
    for e in ir.get("entity_templates") or []:
        mark(e.get("display_name") or "", e.get("id") or "")
        vis = e.get("visuals") or []
        for v in vis:
            mark(v, e.get("id") or "")
