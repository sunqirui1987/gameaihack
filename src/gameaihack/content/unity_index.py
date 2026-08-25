from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

TOKEN_RE = re.compile(
    r"Chapter(\d{2,3})[/\\]Levels(?:[/\\]Level(\d{2,3})\.asset)?"
    r"|Level(\d{2,3})\.asset",
    re.I,
)


def _ascii_strings(data: bytes, min_len: int = 8) -> list[str]:
    from gameaihack.extract.stringsutil import iter_ascii_strings

    return list(iter_ascii_strings(data, min_len))


def index_unity_levels(merged: Path) -> list[dict]:
    """从 Addressables catalog / bundle 抽出章节-关卡索引（L0）。

    catalog 里常见两种写法：整段路径，或先 `Chapter001/Levels` 再跟 `Level001.asset`。
    章内关号按文件名排序后从 1 起算，不把跨章连号（Level016）当成第 16 关。
    """
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
        _collect_pairs(_ascii_strings(data), path, pairs, chapters)
        evidence_path = path

    levels: list[dict] = []
    if pairs:
        by_ch: dict[int, list[int]] = defaultdict(list)
        for ch, asset_lv in pairs:
            by_ch[ch].append(asset_lv)
        for ch, asset_lvs in sorted(by_ch.items()):
            for seq, asset_lv in enumerate(sorted(set(asset_lvs)), 1):
                src = pairs[(ch, asset_lv)]
                extra = {"chapter": ch, "level": seq}
                if asset_lv != seq:
                    extra["asset_level"] = asset_lv
                levels.append(
                    _lvl(
                        f"ch{ch:03d}_lv{seq:03d}",
                        ch * 1000 + seq,
                        f"第{ch}章第{seq}关",
                        src,
                        extra=extra,
                    )
                )
        have = set(by_ch)
        for ch in sorted(chapters - have):
            levels.append(
                _lvl(
                    f"chapter_{ch:03d}",
                    ch * 1000,
                    f"第{ch}章",
                    evidence_path,
                    extra={"chapter": ch},
                )
            )
    elif chapters:
        for ch in sorted(chapters):
            levels.append(
                _lvl(
                    f"chapter_{ch:03d}",
                    ch * 1000,
                    f"第{ch}章",
                    evidence_path,
                    extra={"chapter": ch},
                )
            )
    if not levels:
        from gameaihack.core.fs import iter_files

        for p in iter_files(merged):
            name = p.name.lower()
            if any(k in name for k in ("chapter", "level", "episode", "saga")) and name.endswith(
                (".bundle", ".unity3d", ".assets")
            ):
                levels.append(_lvl(p.stem[:40], 0, p.stem, p.as_posix(), extra={"bundle": p.name}))
    return levels


def _collect_pairs(
    strings: list[str],
    path: str,
    pairs: dict[tuple[int, int], str],
    chapters: set[int],
) -> None:
    current: int | None = None
    pending: int | None = None
    for s in strings:
        for m in TOKEN_RE.finditer(s):
            ch_s, full_lv, loose_lv = m.group(1), m.group(2), m.group(3)
            if ch_s:
                ch = int(ch_s)
                if not (1 <= ch <= 200):
                    continue
                chapters.add(ch)
                current = ch
                if full_lv:
                    lv = int(full_lv)
                    if 1 <= lv <= 80:
                        pairs[(ch, lv)] = path
                    pending = None
                    continue
                if pending is not None:
                    pairs[(ch, pending)] = path
                    pending = None
                continue
            if not loose_lv:
                continue
            lv = int(loose_lv)
            if not (1 <= lv <= 80):
                continue
            if current is not None:
                pairs[(current, lv)] = path
                pending = None
            else:
                pending = lv


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
