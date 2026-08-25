"""写出 output/策划 的机器骨架。游戏怎么玩由 agent 根据 raw + 美术写，这里不写死某一款游戏。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from gameaihack.publish.level_book import resolve_levels, summarize_chapters, write_level_book

CHAPTERS = [
    ("00-封面.md", "封面"),
    ("01-产品定位.md", "产品定位"),
    ("02-核心玩法.md", "核心玩法"),
    ("03-关卡设计.md", "关卡设计"),
    ("04-成长与进度.md", "成长与进度"),
    ("05-经济与商业化.md", "经济与商业化"),
    ("06-系统总表.md", "系统总表"),
    ("07-新手-UI-社交.md", "新手 / 大厅 / 社交"),
    ("08-技术约束.md", "平台与发布"),
    ("09-未知与下一步.md", "运营与内容"),
]


def write_gamebook(dest: Path, ir: dict, ctx: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    art = _Art(dest.parent / "美术")
    job_dir = Path(ctx["_job_dir"]) if ctx.get("_job_dir") else dest.parent.parent
    resolved = resolve_levels(ir, job_dir)
    ir_view = dict(ir)
    ir_view["levels"] = resolved
    meta = _Meta(dest, ir_view, ctx, art)
    writers = {
        "00-封面.md": _cover,
        "01-产品定位.md": _identity,
        "02-核心玩法.md": _play,
        "03-关卡设计.md": _levels,
        "04-成长与进度.md": _growth,
        "05-经济与商业化.md": _economy,
        "06-系统总表.md": _systems,
        "07-新手-UI-社交.md": _ux,
        "08-技术约束.md": _tech,
        "09-未知与下一步.md": _ops,
    }
    for fn, _title in CHAPTERS:
        (dest / fn).write_text(writers[fn](meta), encoding="utf-8")
    (dest / "README.md").write_text(_toc(meta), encoding="utf-8")
    _write_art_guides(dest / "图鉴", meta)
    write_level_book(dest / "关卡", ir_view, title=meta.title, job_dir=job_dir, levels=resolved)
    ai = dest / "ai" / "gdd.md"
    if ai.exists():
        (dest / "附录-agent详述.md").write_text(
            "# 附录：模型长文\n\n"
            "和正文章节不一致时，以 agent 写的正文为准。\n\n"
            + ai.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


class _Art:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.by_folder: dict[str, list[Path]] = {}
        if root.is_dir():
            for p in root.rglob("*.png"):
                rel = p.relative_to(root)
                top = rel.parts[0] if rel.parts else "其他"
                self.by_folder.setdefault(top, []).append(rel)
                self.by_folder.setdefault("_all", []).append(rel)

    def pick(self, *needles: str, folder: str | None = None, limit: int = 4) -> list[Path]:
        pool = list(self.by_folder.get(folder or "_all") or [])
        if needles:
            low = [n.lower() for n in needles]
            hit = [p for p in pool if any(n in p.as_posix().lower() for n in low)]
            pool = hit or pool
        pool.sort(
            key=lambda p: (
                0 if not re.search(r"[0-9a-f]{12,}", p.name.lower()) else 1,
                len(p.parts),
                len(p.name),
                p.as_posix().lower(),
            )
        )
        out: list[Path] = []
        seen: set[str] = set()
        for p in pool:
            key = p.name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
            if len(out) >= limit:
                break
        return out

    def md(self, *needles: str, folder: str | None = None, limit: int = 4, prefix: str = "../美术") -> str:
        items = self.pick(*needles, folder=folder, limit=limit)
        if not items:
            return ""
        return "\n\n" + "\n\n".join(f"![]({prefix}/{p.as_posix()})" for p in items) + "\n"

    def folders(self) -> list[str]:
        return sorted(k for k in self.by_folder if not k.startswith("_"))


class _Meta:
    def __init__(self, dest: Path, ir: dict, ctx: dict, art: _Art) -> None:
        self.dest = dest
        self.ir = ir
        self.ctx = ctx
        self.art = art
        self.pkg = ctx.get("package_name") or ""
        self.title = _display_name(dest, ctx)
        self.version = ctx.get("version_name") or ""
        self.genre = ctx.get("genre") or "未判定"
        self.levels = ir.get("levels") or []
        self.n_lv = int(ctx.get("n_lv") or len(self.levels) or 0)
        self.n_ch = int(ctx.get("n_chapters") or _count_chapters(self.levels))


def _display_name(dest: Path, ctx: dict) -> str:
    job = dest.parent.parent
    for cand in (
        job / "raw" / "unpacked" / "container" / "manifest.json",
        job / "unpacked" / "container" / "manifest.json",
    ):
        if not cand.exists():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = data.get("name") or data.get("locales_name")
        if isinstance(name, dict):
            name = name.get("en") or name.get("zh") or next(iter(name.values()), None)
        if name:
            return str(name)
    return ctx.get("package_name") or "游戏"


def _count_chapters(levels: list[dict]) -> int:
    ch = {(lv.get("extra") or {}).get("chapter") for lv in levels}
    ch.discard(None)
    return len(ch)


def _toc(m: _Meta) -> str:
    lines = [
        f"# {m.title} · 策划稿\n",
        f"{m.pkg}  {m.version}\n",
        "完整玩法由 agent 读 raw/ 和美术后写入。关卡表按第几关来写，不当资源清单。\n",
        "这份策划在 TapTap Maker 工程里：上一级就是 `output/`，脚本在 `../scripts/`。\n",
        "| 文档 | 写什么 |",
        "|---|---|",
    ]
    for fn, title in CHAPTERS:
        lines.append(f"| [{fn}]({fn}) | {title} |")
    lines += [
        "| [图鉴/](图鉴/) | 按美术目录对照 |",
        "| [关卡/](关卡/) | 按章关卡 |",
        "",
        "以 agent 正文为准。原画在 [`../美术/`](../美术/)。\n",
    ]
    return "\n".join(lines)


def _cover(m: _Meta) -> str:
    hero = m.art.md(limit=6)
    n_art = sum(len(v) for k, v in m.art.by_folder.items() if k != "_all")
    return "\n".join(
        [
            f"# {m.title}\n",
            f"{m.ctx.get('one_liner') or ''}\n",
            hero,
            "| | |",
            "|---|---|",
            f"| 游戏 | {m.title} |",
            f"| 版本 | {m.version} |",
            f"| 品类 | {m.genre} |",
            f"| 关卡 | {m.n_lv} 关" + (f" · {m.n_ch} 章" if m.n_ch else "") + " |",
            f"| 美术 | {n_art} 张 |",
            "",
            "## 先读这些\n",
            "1. [核心玩法](02-核心玩法.md)",
            "2. [图鉴/](图鉴/)",
            "3. [关卡/](关卡/)",
            "4. [经济与商业化](05-经济与商业化.md)",
            "",
            "玩法细节以 agent 根据本包 raw/ 写出的正文为准。\n",
        ]
    )


def _identity(m: _Meta) -> str:
    pics = m.art.md(limit=3)
    return f"""# 产品定位

{m.title}。品类：{m.genre}。

{pics}

{_claim_lines(m.ir, 1)}
"""


def _play(m: _Meta) -> str:
    pics = m.art.md(limit=6)
    return f"""# 核心玩法

{m.title}。品类 {m.genre}。

{pics}

{_claim_lines(m.ir, 3, 4, 18)}

完整循环、角色技能、胜负条件由 agent 根据 raw/ 补全，不要用别的游戏的规则来填。
"""


def _levels(m: _Meta) -> str:
    summaries = summarize_chapters(m.levels)
    themes = m.art.md(folder="场景", limit=4)
    rows = ["| 章 | 有几关 | 文档 |", "|---|---|---|"]
    for row in summaries:
        ch = row["chapter"]
        rows.append(
            f"| 第 {ch} 章 | {row['how_many']} | [关卡/第{ch:03d}章.md](关卡/第{ch:03d}章.md) |"
        )
    extra = f"\n{chr(10).join(rows)}\n" if summaries else "\n还没有章节索引。\n"
    ch_bit = f"**{m.n_ch}** 章" if m.n_ch else "若干章"
    return f"""# 关卡设计

按章做人话关卡表，见 [关卡/](关卡/)。一共 {ch_bit}。只看到章名的不要当成 1 关。

{themes}
{extra}
每一章写第几关、这一关干什么、通关后开哪一关。砖怎么摆以 raw 解出的为准；解不出就自己摆。
"""


def _growth(m: _Meta) -> str:
    pics = m.art.md(limit=6)
    return f"""# 成长与进度

{pics}

{_claim_lines(m.ir, 8, 9)}

养成线（角色、装备、通行证、收集）由 agent 根据本包系统来写。
"""


def _economy(m: _Meta) -> str:
    pics = m.art.md(limit=6)
    return f"""# 经济与商业化

{pics}

{_claim_lines(m.ir, 10, 11)}

货币、商店、广告点位由 agent 根据本包来写，不套用其它游戏的经济表。
"""


def _systems(m: _Meta) -> str:
    pics = m.art.md(limit=4)
    return f"""# 系统总表

{pics}

{_claim_lines(m.ir)}

大厅有哪些入口、各模式干什么，由 agent 根据本包界面和程序集来列。
"""


def _ux(m: _Meta) -> str:
    pics = m.art.md(limit=4)
    return f"""# 新手、大厅和社交

{pics}

{_claim_lines(m.ir, 12, 13, 14, 15)}
"""


def _tech(m: _Meta) -> str:
    fp = m.ir.get("fingerprint") or {}
    return f"""# 平台与发布

| | |
|---|---|
| 游戏 | {m.title} |
| 包名 | {m.pkg} |
| 版本 | {m.version} |
| 引擎 | {fp.get("engine") or "—"} |
| 热更 | {", ".join(fp.get("hotupdate") or []) or "—"} |
"""


def _ops(m: _Meta) -> str:
    return f"""# 运营与内容

活动、赛季、关卡投放节奏由 agent 根据本包的活动资源和章节结构来写。
"""


def _write_art_guides(dest: Path, m: _Meta) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    toc = [
        f"# 美术图鉴 · {m.title}\n",
        "按本包实际抽出的目录对照。不同游戏目录不同。\n",
        "| 图鉴 | 张数 |",
        "|---|---|",
    ]
    for folder in m.art.folders():
        pngs = m.art.by_folder.get(folder) or []
        if not pngs:
            continue
        fn = f"{folder}.md"
        toc.append(f"| [{fn}]({fn}) | {len(pngs)} |")
        picked = m.art.pick(folder=folder, limit=40)
        lines = [
            f"# {folder} · {m.title}\n",
            f"`美术/{folder}/` 共 {len(pngs)} 张。下面是对照抽样。\n",
        ]
        for p in picked:
            lines.append(f"### {p.stem}\n")
            lines.append(f"![](../../美术/{p.as_posix()})\n")
            lines.append(f"`美术/{p.as_posix()}`\n")
        if len(pngs) > len(picked):
            lines.append(f"其余见 `美术/{folder}/`。\n")
        (dest / fn).write_text("\n".join(lines), encoding="utf-8")
    toc.append("\n每张图用在哪个系统，由 agent 在策划正文里标明。\n")
    (dest / "README.md").write_text("\n".join(toc), encoding="utf-8")


def _claim_lines(ir: dict, *dims: int) -> str:
    want = set(dims)
    lines: list[str] = []
    for c in ir.get("claims") or []:
        if dims and int(c.get("dimension") or 0) not in want:
            continue
        t = re.sub(r"`[^`]+`", "", c.get("text") or "")
        t = re.sub(r"\s+", " ", t).strip(" ：:-")
        if len(t) < 4:
            continue
        if any(k in t.lower() for k in ("unity", "il2cpp", "addressable", "link.xml")):
            continue
        lines.append(f"- {t}")
    if not lines:
        return ""
    return "## 从本包读到的要点\n\n" + "\n".join(lines[:40]) + "\n"
