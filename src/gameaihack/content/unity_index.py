from __future__ import annotations

import re
from pathlib import Path

CHAPTER_DIR_RE = re.compile(r"Chapter(\d{2,3})[/\\]Levels", re.I)
LEVEL_IN_CHAPTER_RE = re.compile(
    r"Chapter(\d{2,3})[/\\]Levels[/\\]Level(\d{2,3})\.asset",
    re.I,
)


def _ascii_strings(data: bytes, min_len: int = 8) -> list[str]:
    from gameaihack.extract.stringsutil import iter_ascii_strings

    return list(iter_ascii_strings(data, min_len))


def index_unity_levels(merged: Path) -> list[dict]:
    """从 Addressables catalog / bundle 文件名抽出章节-关卡索引（L0）。"""
    blobs: list[tuple[str, bytes]] = []
    catalog = merged / "assets/aa/catalog.bin"
    if catalog.exists() and catalog.stat().st_size < 20_000_000:
        blobs.append((catalog.as_posix(), catalog.read_bytes()))
    aa = merged / "assets/aa/Android"
    if aa.exists():
        for p in aa.glob("*chapter*"):
            if p.is_file() and p.stat().st_size < 80_000_000:
                blobs.append((p.as_posix(), p.read_bytes()[:2_000_000]))
    pairs: dict[tuple[int, int], str] = {}
    chapters: set[int] = set()
    evidence_path = "assets/aa/catalog.bin"
    for path, data in blobs:
        text = "\n".join(_ascii_strings(data))
        for m in LEVEL_IN_CHAPTER_RE.finditer(text):
            ch, lv = int(m.group(1)), int(m.group(2))
            if 1 <= ch <= 200 and 1 <= lv <= 80:
                pairs[(ch, lv)] = path
                chapters.add(ch)
        for m in CHAPTER_DIR_RE.finditer(text):
            ch = int(m.group(1))
            if 1 <= ch <= 200:
                chapters.add(ch)
        evidence_path = path

    levels: list[dict] = []
    if pairs:
        for (ch, lv), src in sorted(pairs.items()):
            levels.append(
                _lvl(
                    f"ch{ch:03d}_lv{lv:03d}",
                    ch * 1000 + lv,
                    f"Chapter {ch} · Level {lv}",
                    src,
                    extra={"chapter": ch, "level": lv},
                )
            )
        have = {ch for ch, _ in pairs}
        for ch in sorted(chapters - have):
            levels.append(
                _lvl(
                    f"chapter_{ch:03d}",
                    ch * 1000,
                    f"Chapter {ch}",
                    evidence_path,
                    extra={"chapter": ch},
                )
            )
    elif chapters:
        for ch in sorted(chapters):
            levels.append(
                _lvl(
                    f"chapter_{ch:03d}",
                    ch,
                    f"Chapter {ch}",
                    evidence_path,
                    extra={"chapter": ch},
                )
            )
    # bundle 文件名兜底
    if not levels:
        from gameaihack.core.fs import iter_files

        for p in iter_files(merged):
            name = p.name.lower()
            if any(k in name for k in ("chapter", "level", "episode", "saga")) and name.endswith(
                (".bundle", ".unity3d", ".assets")
            ):
                levels.append(_lvl(p.stem[:40], 0, p.stem, p.as_posix(), extra={"bundle": p.name}))
    return levels


def _lvl(lid: str, index: int, name: str, src: str, extra: dict) -> dict:
    return {
        "id": lid,
        "index": index,
        "name": name,
        "kind": "unity_addressables",
        "rebuild_grade": "L0",
        "size": None,
        "unlock": {"requires": [], "stars": 0},
        "win": [],
        "lose": [],
        "stars": [],
        "layers": [],
        "entities": [],
        "triggers": [],
        "waves": [],
        "preview": None,
        "teaching": [],
        "evidence": [{"path": src, "extractor": "unity_catalog", "locator": lid}],
        "extra": extra,
    }
