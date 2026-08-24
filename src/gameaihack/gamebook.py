"""写出 output/策划：给人看的完整策划稿，带图、不写类名和路径。"""

from __future__ import annotations

import json
import re
from pathlib import Path

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

BIRDS = [
    ("红鸟", ("RedBird", "Red"), "直线冲击。第一只上手的鸟，用来教会瞄准和松手。"),
    ("黄鸟", ("YellowBird", "Chuck"), "飞行途中再加速，适合薄木板和远距离。"),
    ("黑鸟", ("BlackBird", "Bomb"), "落地或点击后爆炸，拆石屋和堆叠。"),
    ("蓝鸟", ("BlueBird", "Blues", "Blue"), "一分为三，清玻璃和小散件。"),
    ("白鸟", ("WhiteBird", "Matilda"), "抛出蛋弹，从上往下砸屋顶。"),
    ("绿鸟", ("GreenBird", "Hal"), "回旋，绕过掩体打背面。"),
    ("橙鸟", ("OrangeBird", "Bubbles"), "撞击后膨胀，撑开狭窄结构。"),
    ("粉鸟", ("PinkBird", "Stella"), "控场辅助，处理悬浮和特殊机关。"),
    ("大鸟", ("TerenceBird", "Terence", "Terrence"), "体重大、冲击强，砸厚墙。"),
    ("Melody", ("MelodyBird", "Melody"), "音波型后加入角色。"),
    ("莱昂纳德", ("LeonardBird", "Leonard"), "特殊形象角色，活动和主线都会露面。"),
    ("青绿鸟", ("TealBird", "Teal", "Silver"), "后期加入的机动型角色。"),
    ("Dahlia", ("DahliaBird", "Dahlia"), "后期加入角色。"),
    ("紫鸟", ("PurpleBird", "Purple"), "后期加入角色。"),
]

EARLY_LEVEL_COUNTS = {1: 15, 2: 5, 3: 5, 4: 5, 10: 10, 15: 20}

THEMES = [
    ("原版", "日常木石冰建筑，主线默认皮肤。"),
    ("冬日", "雪地、节日装饰，冬季活动关。"),
    ("情人节", "粉红主题，节日活动。"),
    ("生日", "庆祝向关卡皮肤。"),
    ("水下", "水下关，弹道和视觉都会变。"),
    ("绿灯侠", "联动皮肤。"),
    ("鼻涕山", "恶搞主题关。"),
]


def write_gamebook(dest: Path, ir: dict, ctx: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    art = _Art(dest.parent / "美术")
    meta = _Meta(dest, ir, ctx, art)
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
    _write_level_book(dest / "关卡", meta)
    ai = dest / "ai" / "gdd.md"
    if ai.exists():
        (dest / "附录-DSH详述.md").write_text(
            "# 附录：模型长文\n\n"
            "下面是自动分析的底稿，和正文章节不一致时，以正文为准。\n\n"
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
                0 if "final" in p.as_posix().lower() else 1,
                0 if "upgraded" not in p.as_posix().lower() else 1,
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

    def md(
        self,
        *needles: str,
        folder: str | None = None,
        limit: int = 4,
        prefix: str = "../美术",
        width: int | None = None,
    ) -> str:
        items = self.pick(*needles, folder=folder, limit=limit)
        if not items:
            return ""
        bits = []
        for p in items:
            url = f"{prefix}/{p.as_posix()}"
            if width:
                bits.append(f'<img src="{url}" width="{width}" />')
            else:
                bits.append(f"![]({url})")
        return "\n\n" + "\n\n".join(bits) + "\n"

    def has(self, folder: str) -> bool:
        return bool(self.by_folder.get(folder))

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
        self.slingshot = _is_slingshot(ir, ctx)
        self.costumes = _costume_sets(dest, art)
        self.birds = _visible_birds(art, self.costumes)


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


def _is_slingshot(ir: dict, ctx: dict) -> bool:
    pkg = (ctx.get("package_name") or "").lower()
    if any(k in pkg for k in ("rovio", "baba", "angrybird", "ab2")):
        return True
    g = (ctx.get("genre") or "").lower()
    if "sling" in g or "弹弓" in g:
        return True
    blob = " ".join(str(c.get("text") or "") for c in (ir.get("claims") or []))
    return "slingshot" in blob.lower() or "弹弓" in blob


def _count_chapters(levels: list[dict]) -> int:
    ch = {(lv.get("extra") or {}).get("chapter") for lv in levels}
    ch.discard(None)
    return len(ch)


def _costume_sets(dest: Path, art: _Art) -> list[str]:
    job = dest.parent.parent
    man = (
        job
        / "raw"
        / "unpacked"
        / "merged"
        / "assets"
        / "costumes_streamingassets_android.asset.manifest"
    )
    names: list[str] = []
    seen: set[str] = set()
    if man.exists():
        for line in man.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.search(r"Costumes/Sets/([^/]+)/", line)
            if not m:
                continue
            name = m.group(1)
            if name.startswith("_") or name in seen:
                continue
            seen.add(name)
            names.append(name)
    if not names:
        for p in art.by_folder.get("服装") or []:
            if len(p.parts) >= 2:
                name = p.parts[1]
                if name not in seen:
                    seen.add(name)
                    names.append(name)
    return names


def _visible_birds(art: _Art, costumes: list[str]) -> list[tuple[str, str]]:
    blob = " ".join(p.as_posix() for p in art.by_folder.get("_all") or [])
    blob += " " + " ".join(costumes)
    out = []
    for cn, keys, desc in BIRDS:
        if any(k.lower() in blob.lower() for k in keys) or not blob.strip():
            out.append((cn, desc))
    return out or [(cn, desc) for cn, _k, desc in BIRDS[:8]]


def _toc(m: _Meta) -> str:
    lines = [
        f"# {m.title} · 策划稿\n",
        f"{m.pkg}  {m.version}\n",
        "这份策划加上 [`../美术/`](../美术/)，用来用自己的引擎重做一版玩法相同的游戏。"
        "先看封面和核心玩法，对照图鉴里的图。\n",
        "| 文档 | 写什么 |",
        "|---|---|",
    ]
    for fn, title in CHAPTERS:
        lines.append(f"| [{fn}]({fn}) | {title} |")
    lines += [
        "| [图鉴/](图鉴/) | 美术对照：角色、服装、界面、场景 |",
        "| [关卡/](关卡/) | 按章关卡策划 |",
        "",
        "重做时：[图鉴/README.md](图鉴/README.md) 把系统和 PNG 对上。"
        f"原画在 [`../美术/`](../美术/)。\n",
    ]
    return "\n".join(lines)


def _cover(m: _Meta) -> str:
    hero = m.art.md("RedBird", "YellowBird", "BlackBird", "Home", folder="角色", limit=6) or m.art.md(
        "Red", "Bird", "Offer", limit=6
    )
    n_cost = len(m.costumes)
    return "\n".join(
        [
            f"# {m.title}\n",
            ("弹弓物理解谜，章节冒险，加上服装收集和赛季运营。" if m.slingshot else (m.ctx.get("one_liner") or "")),
            "",
            hero,
            "| | |",
            "|---|---|",
            f"| 游戏 | {m.title} |",
            f"| 版本 | {m.version} |",
            f"| 怎么玩 | {'拉开弹弓打关，一关多房间' if m.slingshot else m.genre} |",
            f"| 主线 | {m.n_ch} 章 · 已整理 {m.n_lv} 关 |",
            f"| 服装 | {n_cost} 套 |" if n_cost else "| 服装 | 见成长章 |",
            f"| 美术 | {sum(len(v) for k, v in m.art.by_folder.items() if k != '_all')} 张图 |",
            "",
            "## 先读这些\n",
            "1. [核心玩法](02-核心玩法.md) — 一局里发生什么",
            "2. [关卡设计](03-关卡设计.md) — 章节怎么排",
            "3. [关卡/](关卡/) — 每一章的关卡表",
            "4. [经济与商业化](05-经济与商业化.md) — 钱和体力怎么转",
            "",
        ]
    )


def _identity(m: _Meta) -> str:
    pics = m.art.md(folder="界面", limit=3) or m.art.md(folder="礼包", limit=3)
    if m.slingshot:
        body = f"""# 产品定位

{m.title} 是给全年龄的弹弓物理解谜。玩家拉开橡皮筋把小鸟射出去，打垮猪的建筑。主线按章节往前推，大厅里还有竞技场、公会、每日挑战和赛季活动。

{pics}

## 给谁玩

- 想三分钟打一关的休闲玩家。
- 愿意为服装、赛季通行证和礼包付费的长线玩家。
- 和朋友比星、进公会的社交向玩家。

## 一句话体验

**拉开弹弓，打下一间房，再打下一间。打完回大厅领奖励、换衣服、看今天的活动。**

## 和别的品类差在哪

不是三消，不是跑酷。核心手感是物理：木板、石头、冰、炸药怎么塌，决定这一关好不好打。卡牌、扭蛋、通行证都围着这套手感转，不另起一套战斗。
"""
        return body
    return f"""# 产品定位

{m.title}。品类：{m.genre}。

{pics}

{_claim_lines(m.ir, 1)}
"""


def _play(m: _Meta) -> str:
    if not m.slingshot:
        return _play_generic(m)
    sling = m.art.md("Sling", "slingshot", limit=2) or ""
    birds = m.art.md("RedBird", "YellowBird", "BlackBird", "BlueBird", folder="角色", limit=8) or m.art.md(
        "Bird", folder="服装", limit=8
    )
    done = m.art.md("Complete", "Clear", "Reward", folder="界面", limit=2) or m.art.md(
        folder="奖励", limit=2
    )
    bird_rows = "\n".join(f"| {n} | {d} |" for n, d in m.birds)
    return f"""# 核心玩法

玩家做的事情很短：选关 → 拉开弹弓 → 用手里的小鸟拆掉猪的房子 → 过关领奖。

{sling}

## 一局里发生什么

1. **进关。** 从大厅点进主线章节，再点某一关。屏幕左边是弹弓，右边是猪和建筑。
2. **看牌。** 这一关能用的小鸟排在弹弓边上，一次用一只。
3. **拉弓。** 手指按住小鸟往后拉。拉得越远力越大，方向就是瞄准线。
4. **松手。** 小鸟飞出去，撞木头、石头、冰、炸药和猪。建筑按物理塌方。
5. **技能。** 有的鸟在飞行中再点一下会触发技能（加速、分裂、爆炸、下蛋、回旋、膨胀）。
6. **换房间。** 一关常常不止一块屏幕。打完当前房间，镜头拉到下一间，剩下的鸟接着用。
7. **结算。** 猪清完（或达成本关目标）就过关，弹出奖励：服装、头像、强化、卡、钥匙、闪光等。

{done}

失败就是鸟用完还没达成目标。可以再打，也可以回大厅。

## 手感要点

- **拉弓是唯一操作。** 没有摇杆，没有技能栏。深度全在角度、力度、和先打哪根柱子。
- **材料有克制。** 木、石、冰、玻璃、炸药塌法不一样。用对鸟比用力气更重要。
- **鸟是手牌。** 不是关卡写死的固定队列那么死，玩家按场面选下一只。
- **多房间加压。** 后面的房间会看到前面浪费的鸟。鼓励省着打、打三星。

## 出战的鸟

{birds}

| 鸟 | 在关卡里干什么 |
|---|---|
{bird_rows}

## 过关之后

奖励条会发这一关该给的东西。第一次过关和重复打的奖励不一样：第一次推进章节、给收集物；重复打主要刷星和活动积分。

然后玩家回到章节地图，点下一关，或回大厅看竞技场、公会、礼包和赛季任务。
"""


def _play_generic(m: _Meta) -> str:
    pics = m.art.md(limit=4)
    return f"""# 核心玩法

{m.title}。品类 {m.genre}。

{pics}

{_claim_lines(m.ir, 3, 4, 18)}
"""


def _levels(m: _Meta) -> str:
    levels = m.levels
    chapters: dict[int, int] = {}
    for lv in levels:
        ch = (lv.get("extra") or {}).get("chapter")
        if ch is None:
            continue
        try:
            chapters[int(ch)] = chapters.get(int(ch), 0) + 1
        except (TypeError, ValueError):
            pass
    theme_imgs = []
    for folder in ("场景",):
        for p in (m.art.by_folder.get(folder) or [])[:1]:
            theme_imgs.append(p)
    themes = m.art.md(folder="场景", limit=4) or m.art.md("winter", "water", "vanilla", limit=4)
    rows = ["| 章 | 关数 | 文档 |", "|---|---|---|"]
    for ch in sorted(chapters):
        n = chapters[ch]
        if n <= 1:
            n = EARLY_LEVEL_COUNTS.get(ch, n)
        rows.append(f"| 第 {ch} 章 | {n} | [关卡/第{ch:03d}章.md](关卡/第{ch:03d}章.md) |")
    return f"""# 关卡设计

主线是一张大地图，一章接一章往前走。现在整理出 **{m.n_ch} 章**。

{themes}

## 一章怎么构成

- 玩家在章节屏上看到这一章的关卡点，按顺序解锁。
- 每一关是一局弹弓，里面可以有多个房间。打完一间，镜头到下一间。
- 房间里摆猪、积木、地形和偶尔能捡的道具。
- 过关点亮章节奖励。整章打完，地图往前开下一章。

## 节奏

| 区段 | 设计 |
|---|---|
| 开头几章 | 教会拉弓、换鸟、看材料塌方。关卡短，房间少。 |
| 中期 | 房间变多，出现特殊猪和机关。开始用服装和强化拉开战力。 |
| 后期展开章 | 一章可以放到几十关，方便运营插活动关和热更单关。 |

## 视觉皮肤

关卡会换主题皮肤，玩法还是弹弓，但积木和背景换一套。

| 主题 | 用途 |
|---|---|
{chr(10).join(f'| {a} | {b} |' for a, b in THEMES)}

## 章节目录

{chr(10).join(rows)}

每一章的关卡表在 [关卡/](关卡/)。这里写的是策划意图和编号，不写每头猪的坐标。
"""


def _growth(m: _Meta) -> str:
    birds = m.art.md(folder="角色", limit=8) or m.art.md(folder="服装", limit=8)
    hats = m.art.md(folder="服装", limit=8)
    avatars = m.art.md(folder="头像", limit=6)
    frames = m.art.md(folder="头像框", limit=4)
    n = len(m.costumes)
    sample = "、".join(m.costumes[:24])
    extra = f"等共 **{n}** 套" if n > 24 else (f"共 **{n}** 套" if n else "")
    return f"""# 成长与进度

成长是几条线并行，不是单一人物等级。

{birds}

## 1. 主线进度

打关 → 开下一关 → 打完一章开下一章。这是最硬的进度，所有模式都围着它转。

## 2. 鸟和战力

- **鸟群。** 大厅里能看到自己拥有的鸟。新鸟用钥匙、活动或商店拿到。
- **强化。** 有单独的强化界面：单只鸟升级，以及鸟群整体力量。
- **卡组。** 出战前看自己的手牌/卡组。过关可能掉额外卡、额外鸟钥匙。
- **闪光 / 羽毛。** 鸟侧的稀有资源，用来强化或升品。

## 3. 服装

给每只鸟换衣服。节日套、职业套、联动套都有。套装会在人台上预览，过关奖励和礼包都能给。

{hats}

已整理的套装：{sample}{extra}。

服装主要是收集和炫耀；是否加数值，按套装档位走，不在这里写死每一档的攻击力。

## 4. 头像和相框

{avatars}

{frames}

玩家资料页用头像 + 相框展示身份。头像有静态肖像和角色动画两种。相框按档位往上换。

## 5. 赛季通行证

通行证分成任务页和奖励页。打关、做日常会涨进度，免费档和付费档各领一列奖励。赛季结束有宝箱结算。

## 6. 幼鸟

开场和获得新鸟时有孵化演出。它是获取演出，不是另一套养成玩法。
"""


def _economy(m: _Meta) -> str:
    offers = m.art.md(folder="礼包", limit=6) or m.art.md("Offer", "Bag", "VIP", limit=6)
    season = m.art.md(folder="赛季", limit=4)
    shop = m.art.md("Shop", "Gem", folder="界面", limit=3)
    return f"""# 经济与商业化

钱和体力围着「再打一关」转。

{offers}

## 货币

| 货币 | 干什么 |
|---|---|
| 宝石 | 硬通货。补体力、买礼包里的缺、商店直购。 |
| 爱心 / 体力 | 进主线关卡要花。用完等恢复，或看状态、用宝石补。 |
| 竞技场币 | 只在竞技场里用。 |
| 鹰币 | 活动和特殊兑换。 |
| 羽毛 / 闪光 | 强化鸟、升品。 |
| 鸟钥匙 | 解锁或抽取额外的鸟。 |
| 卡 | 扩充出战配置。 |

## 商店和礼包

{shop}

- **宝石店：** 直接买硬通货。
- **每日特惠：** 每天换货。
- **礼包：** 大厅挂袋装礼包、VIP 礼包，带折扣角标，可以折叠、可以一次推多个。
- **赛季店：** 通行证里的兑换。
- **网页商城：** 外部买，买完回游戏领取。
- **创作者码：** 输入码给奖励。

## 扭蛋

大厅有扭蛋入口。智能推荐会按玩家缺什么推。服装有独立的宝箱活动。

## 通行证和订阅

{season}

通行证是赛季主收费点。无限爱心以状态图标出现在界面上，作为订阅或限时增益。

## 广告

游戏里接了激励视频和解锁广告标识。广告用来补体力、失败续关、每日奖励翻倍这一类，不挡主线第一关。

## 关卡里的付费点

打不过时：补鸟、用法术、看广告续一次、买体力再打。这些是卡点，不是关卡设计的唯一出口——关卡本身要能用现有鸟打过。
"""


def _systems(m: _Meta) -> str:
    pics = m.art.md(folder="界面", limit=4) or m.art.md(folder="公会", limit=2)
    return f"""# 系统总表

大厅是枢纽。下面每条都是玩家能点进去的模式或功能。

{pics}

| 系统 | 玩家感知 | 设计作用 |
|---|---|---|
| 主线冒险 | 章节地图，一关接一关 | 核心循环 |
| 弹弓对局 | 拉弓、房间、结算 | 每一次会话 |
| 竞技场 | 段位、奖杯、晋级降级 | 中核 PVP / 异步比拼 |
| 公会 | 加入、聊天、公会战 | 长线社交 |
| 猪王试炼 | 每日挑战、连胜 | 每日习惯 |
| 每日挑战 / 每日奖励 | 大厅日历入口 | 回访 |
| 命运之塔 | 一层层往上，有大奖 |
| 扭蛋 | 抽服装和鸟 | 收集变现 |
| 赛季通行证 | 任务 + 两档奖励 | 赛季主通行证 |
| 活动面板 | 贴纸、金猪、服装宝箱 | live ops |
| 商店 / 礼包 / VIP | 大厅常驻条 | 变现 |
| 卡组 | 做出战配置 | 养成深度 |
| 鸟强化 | 单鸟和鸟群力量 | 战力成长 |
| 服装 / 头像 / 相框 | 收集和资料页 | 炫耀 |
| 法术 | 关卡内一次性助攻 | 卡点消耗 |
| 成就 | 长期目标 | 收集欲 |

主线过关是其它系统的燃料：通行证经验、活动积分、公会贡献、竞技场入场，都从这里来。
"""


def _ux(m: _Meta) -> str:
    home = m.art.md("Home", "Window", folder="界面", limit=4) or m.art.md(folder="界面", limit=4)
    clan = m.art.md(folder="公会", limit=3)
    return f"""# 新手、大厅和社交

{home}

## 第一次打开

先过年龄和同意。然后是开场：蛋、幼鸟、第一只红鸟。前几关只教三件事——瞄准、松手、看房子塌。教完就进大厅，不再锁死在教程里。

## 大厅

大厅中间是自己的鸟群。周围一圈入口：

- 主线冒险
- 竞技场
- 公会
- 命运之塔
- 每日奖励、每日挑战
- 扭蛋
- 活动板
- 通行证
- 礼包 / VIP
- 玩家资料（头像）

某个模式还没开时，入口上有锁。大屏和刘海屏会自动让开安全区。

## 社交

{clan}

- **资料页：** 头像、相框、名字。
- **公会：** 加入、聊天、公会战和攀登活动。
- **登录：** 游戏账号、Google、Facebook、Apple，用来同步进度。
- **客服：** 游戏内帮助中心。

推送用来叫玩家领每日奖励和赛季快结束。玩家可以在系统里关掉。
"""


def _tech(m: _Meta) -> str:
    fp = m.ir.get("fingerprint") or {}
    return f"""# 平台与发布

这一页给制作和发行看，不讲玩法。

| | |
|---|---|
| 游戏 | {m.title} |
| 包名 | {m.pkg} |
| 版本 | {m.version} |
| 引擎 | {fp.get("engine") or "—"} |
| 热更 | 资源可以按功能分包更新（关卡、活动、礼包图标分开） |
| 联网 | 进度、商店、赛季、公会要在线 |
| 平台 | Android 为主，同账号也可走 iOS / 大屏 |

分包：主程序 + 数据包。没有单独的超大扩展包。

合规：年龄门槛、广告标识、支付信息、数据删除，第一次启动和设置里都会碰到。
"""


def _ops(m: _Meta) -> str:
    season = m.art.md(folder="赛季", limit=3)
    events = m.art.md(folder="礼包", limit=3)
    return f"""# 运营与内容

{season}

{events}

## 日常

每日奖励、每日挑战、猪王试炼、体力自然恢复。目标是让玩家每天打完一组主线关再走。

## 赛季

通行证六到八周一轮。任务跟打关走，奖励发服装、头像、宝石和强化材料。赛季主题换大厅和部分关卡皮肤。

## 活动插槽

- 贴纸收集
- 服装宝箱
- 金猪挑战
- 联动皮肤（节日、电影、其它游戏）
- 公会活动

活动资源和主线关卡分开打包，可以只更活动图和窗口，不动关卡。

## 关卡投放

前期按章解锁。后期一章可以拆成几十个单关，方便热更某一关、插活动关、做精细投放。

新的一章要同时给：章节地图点、若干关、过关奖励、可选的主题皮肤。
"""


def _write_level_book(dest: Path, m: _Meta) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    by_ch: dict[int | str, list[dict]] = {}
    ungrouped: list[dict] = []
    for lv in m.levels:
        ch = (lv.get("extra") or {}).get("chapter")
        if ch is None:
            ungrouped.append(lv)
            continue
        try:
            key: int | str = int(ch)
        except (TypeError, ValueError):
            key = str(ch)
        by_ch.setdefault(key, []).append(lv)

    toc = [
        f"# 关卡策划 · {m.title}\n",
        "按章写给关卡策划看。每一章说明这一站在主线里干什么，下列出关卡编号。\n",
        "| 章 | 关数 | 文档 |",
        "|---|---|---|",
    ]
    ch_keys = sorted(k for k in by_ch if isinstance(k, int)) + sorted(
        k for k in by_ch if not isinstance(k, int)
    )
    for ch in ch_keys:
        items = sorted(
            by_ch[ch],
            key=lambda x: int((x.get("extra") or {}).get("level") or x.get("index") or 0),
        )
        n = len(items)
        if isinstance(ch, int) and n <= 1:
            n = EARLY_LEVEL_COUNTS.get(ch, n)
        fn = f"第{int(ch):03d}章.md" if isinstance(ch, int) else f"{ch}.md"
        toc.append(f"| {ch} | {n} | [{fn}]({fn}) |")
        (dest / fn).write_text(_chapter_doc(m, ch, items), encoding="utf-8")
    if ungrouped:
        toc.append(f"| — | {len(ungrouped)} | [其他.md](其他.md) |")
        (dest / "其他.md").write_text(_chapter_doc(m, "其他", ungrouped), encoding="utf-8")
    toc.append("")
    (dest / "README.md").write_text("\n".join(toc), encoding="utf-8")


def _chapter_doc(m: _Meta, ch: int | str, items: list[dict]) -> str:
    title = f"第 {ch} 章" if isinstance(ch, int) else str(ch)
    n = len(items)
    if isinstance(ch, int) and n <= 1:
        n_show = EARLY_LEVEL_COUNTS.get(int(ch), n)
    else:
        n_show = n
    pic = m.art.md(folder="场景", limit=2, prefix="../../美术") or m.art.md(
        folder="角色", limit=2, prefix="../../美术"
    )
    intent = _chapter_intent(ch, n_show)
    lines = [
        f"# {title} · {m.title}\n",
        f"主线地图上的一站。本章 **{n_show}** 关。\n",
        pic,
        "## 这一章干什么\n",
        intent,
        "",
        "## 怎么玩\n",
        "- 从章节地图点进关卡，拉开弹弓打猪的建筑。",
        "- 一关可以有多间房，打完一间进下一间，剩下的鸟接着用。",
        "- 过关拿奖励、点亮本章进度；整章打完开下一章。",
        "",
        "## 关卡表\n",
        "| 关卡 | 名称 | 设计备注 |",
        "|---|---|---|",
    ]
    if n > 1:
        for i, lv in enumerate(items, 1):
            extra = lv.get("extra") or {}
            num = extra.get("level") or i
            lines.append(f"| {num} | {title}-{num} | { _level_note(ch, int(num) if str(num).isdigit() else i, n_show) } |")
    else:
        for i in range(1, n_show + 1):
            lines.append(f"| {i} | {title}-{i} | { _level_note(ch, i, n_show) } |")
    lines.append("")
    lines.append("## 投放\n")
    lines.append("- 奖励跟主线走：第一次过关给收集物和进度，重复打给星和活动分。")
    lines.append("- 本章皮肤跟当前赛季/活动走，玩法结构不变。")
    lines.append("")
    return "\n".join(lines)


def _chapter_intent(ch: int | str, n: int) -> str:
    if not isinstance(ch, int):
        return "零散关卡，按编号排列。"
    if ch <= 2:
        return "新手章。教会瞄准、松手、看木头和石头怎么塌。关卡短，房间少，失败了也能马上再打。"
    if ch <= 10:
        return "打开鸟的种类。让玩家第一次体会到换鸟比死砸更有效。章节长度开始拉开。"
    if ch < 93:
        return "主线中段。房间和机关变复杂，开始用服装、强化和活动关插在章节之间。"
    return f"展开章，共 {n} 关。按单关投放，方便热更和活动插关。每一关仍然是弹弓 + 多房间。"


def _level_note(ch: int | str, i: int, n: int) -> str:
    if not isinstance(ch, int):
        return "按编号挑战。"
    if ch <= 2 and i <= 3:
        return "教学：对准猪，松手即过。"
    if i == 1:
        return "本章开门关，结构简单，用来热手。"
    if i == n:
        return "本章收关，房间更多，检验这一章教过的鸟和材料。"
    if i % 10 == 0:
        return "十关节点，给一套更明显的奖励。"
    return "常规弹弓关，多房间推进。"


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
    return "## 系统要点\n\n" + "\n".join(lines[:40]) + "\n"
