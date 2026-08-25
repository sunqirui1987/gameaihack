"""按章写出给人看的关卡策划，不当解包资源清单。"""

from __future__ import annotations

from pathlib import Path

REMAKE_SHORT = 5
STUB_FILES = ("03-关卡.md", "04-数据表.md", "05-大厅成长商店.md")


def write_level_book(
    dest: Path,
    ir: dict,
    *,
    title: str = "",
    job_dir: Path | None = None,
    levels: list[dict] | None = None,
) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    items = list(levels) if levels is not None else resolve_levels(ir, job_dir)
    chapters, ungrouped = group_levels(items)
    for old in dest.glob("第*章.md"):
        try:
            old.unlink()
        except OSError:
            pass
    other = dest / "其他.md"
    if other.is_file():
        try:
            other.unlink()
        except OSError:
            pass

    summaries = summarize_chapters(items)
    last_ch = summaries[-1]["chapter"] if summaries else 0
    toc = [
        "# 关卡\n",
        _overview(summaries, title),
        "## 先做这些\n",
        "1. 第 1 章第 1 关，先做出能打完的一局。",
        "2. 把第 1 章做完，通关一关开下一关。",
        "3. 再做已经能数清关数的短章。",
        "4. 只看到章名、看不到每一关的，先按每章 5 关自己摆，不要当成原作关数。",
        "",
        "砖怎么摆包里没有。在 TapTap Maker 的 2D 物理场景里按 [02-核心玩法.md](../02-核心玩法.md) 摆。",
        "不要把索引条数当成「已经解出这么多张关卡图」。",
        "",
        "## 各章\n",
        "| 章 | 有几关 | 这一章 | 文档 |",
        "|---|---|---|---|",
    ]
    for nums, row in cluster_chapters(summaries):
        span = chapter_span(nums)
        first = nums[0]
        fn = f"第{first:03d}章.md"
        if len(nums) == 1:
            doc = f"[{fn}]({fn})"
            how = row["how_many"]
        else:
            last = nums[-1]
            doc = f"[第{first:03d}章](第{first:03d}章.md) … [第{last:03d}章](第{last:03d}章.md)"
            how = f"每章 {row['count']} 关" if row["known"] else "关数未知"
        toc.append(f"| {span} | {how} | {row['what']} | {doc} |")
    toc.append("")
    toc.append("## 怎么做一关\n")
    toc.append("每一关在 Maker 里至少一个物理场：玩家在一侧，目标在另一侧。通关第 N 关开第 N+1 关。")
    toc.append("字段和星级占位见 [03-关卡设计.md](../03-关卡设计.md)。")
    toc.append("")
    (dest / "README.md").write_text("\n".join(toc), encoding="utf-8")

    for ch, ch_items in chapters.items():
        fn = f"第{int(ch):03d}章.md" if isinstance(ch, int) else f"{ch}.md"
        (dest / fn).write_text(chapter_markdown(ch, ch_items, last_ch=last_ch), encoding="utf-8")
    if ungrouped:
        (dest / "其他.md").write_text(_ungrouped_markdown(ungrouped), encoding="utf-8")


def resolve_levels(ir: dict, job_dir: Path | None) -> list[dict]:
    base = list(ir.get("levels") or [])
    if job_dir is None:
        return base
    merged = _merged_root(Path(job_dir))
    if merged is None:
        return base
    from gameaihack.content.unity_index import index_unity_levels

    catalog = index_unity_levels(merged)
    if not catalog:
        return base
    return merge_level_indexes(base, catalog)


def _merged_root(job_dir: Path) -> Path | None:
    from gameaihack.core.layout import unpack_dir

    unpacked = unpack_dir(job_dir)
    for cand in (unpacked / "merged", unpacked):
        if (cand / "assets/aa/catalog.bin").is_file() or (cand / "assets/aa/Android").is_dir():
            return cand
    return None


def merge_level_indexes(base: list[dict], catalog: list[dict]) -> list[dict]:
    """章只是壳、catalog 已经展开到每一关时，用 catalog。"""
    other: list[dict] = []
    base_by: dict[int, list[dict]] = {}
    for lv in base:
        ch = _chapter_of(lv)
        if ch is None:
            other.append(lv)
            continue
        base_by.setdefault(ch, []).append(lv)
    cat_by: dict[int, list[dict]] = {}
    for lv in catalog:
        ch = _chapter_of(lv)
        if ch is None:
            continue
        cat_by.setdefault(ch, []).append(lv)
    out = list(other)
    for ch in sorted(set(base_by) | set(cat_by)):
        b = base_by.get(ch) or []
        c = cat_by.get(ch) or []
        pick = _prefer_expanded(b, c)
        out.extend(pick)
    return out


def _prefer_expanded(base: list[dict], catalog: list[dict]) -> list[dict]:
    if is_chapter_shell(base) and catalog and not is_chapter_shell(catalog):
        return catalog
    if not base and catalog:
        return catalog
    if is_chapter_shell(catalog) and base and not is_chapter_shell(base):
        return base
    if catalog and not is_chapter_shell(catalog) and len(catalog) > len(base):
        return catalog
    return base or catalog


def group_levels(levels: list[dict]) -> tuple[dict[int | str, list[dict]], list[dict]]:
    by_ch: dict[int | str, list[dict]] = {}
    ungrouped: list[dict] = []
    for lv in levels:
        ch = (lv.get("extra") or {}).get("chapter")
        if ch is None:
            ungrouped.append(lv)
            continue
        try:
            key: int | str = int(ch)
        except (TypeError, ValueError):
            key = str(ch)
        by_ch.setdefault(key, []).append(lv)
    for key, items in by_ch.items():
        items.sort(key=_level_sort)
    return by_ch, ungrouped


def summarize_chapters(levels: list[dict]) -> list[dict]:
    by_ch, _ = group_levels(levels)
    out: list[dict] = []
    int_keys = sorted(k for k in by_ch if isinstance(k, int))
    for ch in int_keys:
        items = by_ch[ch]
        shell = is_chapter_shell(items)
        count = 0 if shell else len(items)
        out.append(
            {
                "chapter": ch,
                "count": count,
                "known": not shell,
                "how_many": "关数未知" if shell else f"{count} 关",
                "what": _chapter_kind(ch, not shell, count),
                "items": items,
                "shell": shell,
            }
        )
    return out


def cluster_chapters(summaries: list[dict]) -> list[tuple[list[int], dict]]:
    clusters: list[tuple[list[int], dict]] = []
    for row in summaries:
        key = (row["known"], row["count"], row["what"])
        if clusters:
            nums, prev = clusters[-1]
            prev_key = (prev["known"], prev["count"], prev["what"])
            contiguous = nums[-1] + 1 == row["chapter"]
            if prev_key == key and contiguous and row["what"] != "开头，当教学":
                nums.append(row["chapter"])
                continue
        clusters.append(([row["chapter"]], dict(row)))
    return clusters


def chapter_span(nums: list[int]) -> str:
    nums = sorted(nums)
    if len(nums) == 1:
        return f"第 {nums[0]} 章"
    if nums[-1] - nums[0] + 1 == len(nums):
        return f"第 {nums[0]}～{nums[-1]} 章"
    return "第 " + "、".join(str(n) for n in nums) + " 章"


def is_chapter_shell(items: list[dict]) -> bool:
    if not items:
        return True
    if len(items) != 1:
        return False
    extra = items[0].get("extra") or {}
    if extra.get("level") not in (None, "", 0):
        return False
    lid = str(items[0].get("id") or "")
    return lid.startswith("chapter_") or "level" not in extra


def chapter_markdown(ch: int | str, items: list[dict], *, last_ch: int = 0) -> str:
    title = f"第 {ch} 章" if isinstance(ch, int) else str(ch)
    shell = is_chapter_shell(items)
    n_known = 0 if shell else len(items)
    ch_n = int(ch) if isinstance(ch, int) else 0
    lines = [f"# {title}\n", _chapter_intro(ch_n, n_known, shell), "## 关卡\n"]
    if shell:
        n = REMAKE_SHORT
        lines.append(
            f"原作这一章有几关**未知**。不要当成「只有 1 关」，也不要当成已经解出原作关卡表。"
            f"重做时先做 {n} 关短章：\n"
        )
        lines.extend(_table(ch_n, n, last_ch, remake=True))
    else:
        lines.extend(_table(ch_n, n_known, last_ch, remake=False))
    lines += [
        "",
        "## 怎么做\n",
        "砖怎么摆包里没有。在 Maker 2D 物理场景里按 [02-核心玩法.md](../02-核心玩法.md) 摆刚体。",
        "通关第 N 关开第 N+1 关。本章最后一关通关后开下一章第 1 关。",
        "不要填「原作坐标」。地图节点默认做成普通关；Boss / 骷髅皮有图、没规则，有图再加，不要编机制。",
        "",
    ]
    return "\n".join(lines)


def tidy_design(dest: Path) -> None:
    """删掉 agent 写的「已迁移」重复文件和作业垃圾。"""
    dest = Path(dest)
    if not dest.is_dir():
        return
    for name in STUB_FILES:
        path = dest / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "已迁移" in text[:240]:
            try:
                path.unlink()
            except OSError:
                pass
    junk = dest / "_w.py"
    if junk.is_file():
        try:
            junk.unlink()
        except OSError:
            pass


def _overview(summaries: list[dict], title: str) -> str:
    n_ch = len(summaries)
    known = sum(1 for s in summaries if s["known"])
    unknown = n_ch - known
    bits = []
    if title:
        bits.append(title)
    bits.append(f"一共 **{n_ch}** 章" if n_ch else "还没有章节索引")
    if known and unknown:
        bits.append(f"其中 {known} 章能数清有几关，{unknown} 章只看到章名")
    elif unknown and n_ch:
        bits.append("都只看到章名，每一章有几关未知")
    elif known:
        bits.append("各章关数见下表")
    bits.append("全部没有可抄的布局")
    return "。".join(bits) + "。\n"


def _chapter_kind(ch: int, known: bool, count: int) -> str:
    if not known:
        return "重做先做 5 关"
    if ch == 1:
        return "开头，当教学"
    if count >= 30:
        return "后期长章"
    if count <= 5:
        return "短章"
    return "主线"


def _chapter_intro(ch: int, count: int, shell: bool) -> str:
    if shell or count <= 0:
        body = (
            f"包里只看到第 {ch} 章这个名字，看不到这一章有几关、每一关怎么摆。\n\n"
            "## 这一章在打什么\n\n"
            "跟主线一样。没有证据说这一章换了玩法。\n"
        )
        return body
    if ch == 1:
        return (
            f"全游戏开头。包里能看到 {count} 关，砖怎么摆未知。这一章当教学。\n\n"
            "## 这一章在打什么\n\n"
            "学会主操作，打完每一关的目标。不要在这一章加后面才出现的模式。\n"
        )
    if count >= 30:
        return (
            f"后期长章。包里能看到 {count} 关，仍然没有布局。\n\n"
            "## 这一章在打什么\n\n"
            "继续主线，当后期关卡量。不要当成教学关。\n"
        )
    if count <= 5:
        return (
            f"短章。包里能看到 {count} 关，砖怎么摆未知。\n\n"
            "## 这一章在打什么\n\n"
            "跟主线一样。\n"
        )
    return (
        f"包里能看到 {count} 关，砖怎么摆未知。\n\n"
        "## 这一章在打什么\n\n"
        "跟主线一样。\n"
    )


def _table(ch: int, n: int, last_ch: int, *, remake: bool) -> list[str]:
    lines = [
        "| 关 | 这一关干什么 | 通关后 |",
        "|---|---|---|",
    ]
    for start, end in _segments(n, ch, remake=remake):
        label = f"第 {start} 关" if start == end else f"第 {start}～{end} 关"
        what = _what(ch, start, end, n, remake=remake)
        after = _after(ch, end, n, last_ch)
        lines.append(f"| {label} | {what} | {after} |")
    return lines


def _segments(n: int, ch: int, *, remake: bool) -> list[tuple[int, int]]:
    if n <= 0:
        return []
    if n == 1:
        return [(1, 1)]
    if n == 2:
        return [(1, 1), (2, 2)]
    if remake:
        return [(1, 1), (2, n - 1), (n, n)]
    if ch == 1 and n >= 4:
        return [(1, 1), (2, 2), (3, n - 1), (n, n)]
    if n <= 6:
        return [(i, i) for i in range(1, n + 1)]
    return [(1, 1), (2, n - 1), (n, n)]


def _what(ch: int, start: int, end: int, n: int, *, remake: bool) -> str:
    if remake:
        if start == 1 and end == 1:
            return "接上一章的手感"
        if start == n:
            return "本章收尾"
        return "同一套玩法，略加点难度"
    if ch == 1 and start == 1 and end == 1:
        return "全游戏第一局：学会主操作，打完这一关"
    if ch == 1 and start == 2 and end == 2:
        return "再打一关，熟悉手感"
    if start == 1 and end == 1:
        return "本章第 1 关，接上一章"
    if start == n:
        return "本章最后一关"
    if start != end:
        return "同一套玩法，逐步加难"
    return "继续主线"


def _after(ch: int, end: int, n: int, last_ch: int) -> str:
    if end < n:
        return f"开第 {end + 1} 关"
    if ch and last_ch and ch != last_ch:
        return f"开第 {ch + 1} 章第 1 关"
    return "打完本章"


def _ungrouped_markdown(items: list[dict]) -> str:
    lines = [
        "# 其他关卡\n",
        "还没有分到某一章的关。\n",
        "| 关 | 名字 |",
        "|---|---|",
    ]
    for i, lv in enumerate(items, 1):
        name = str(lv.get("name") or "").strip() or f"第 {i} 关"
        if re_looks_like_id(name):
            name = f"第 {i} 关"
        lines.append(f"| 第 {i} 关 | {name} |")
    lines.append("")
    return "\n".join(lines)


def re_looks_like_id(name: str) -> bool:
    low = name.lower()
    if low.startswith("ch") and "_lv" in low:
        return True
    if low.startswith("chapter"):
        return True
    return False


def _chapter_of(lv: dict) -> int | None:
    ch = (lv.get("extra") or {}).get("chapter")
    if ch is None:
        return None
    try:
        return int(ch)
    except (TypeError, ValueError):
        return None


def _level_sort(lv: dict) -> tuple:
    extra = lv.get("extra") or {}
    try:
        n = int(extra.get("level") or 0)
    except (TypeError, ValueError):
        n = 0
    try:
        idx = int(lv.get("index") or 0)
    except (TypeError, ValueError):
        idx = 0
    return (n or 10**9, idx, str(lv.get("id") or ""))
