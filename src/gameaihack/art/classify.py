"""把贴图分到制作人能用的目录，不按某一款游戏写死角色名。"""

from __future__ import annotations

import re
from pathlib import Path

TECH = re.compile(
    r"(normalmap|_n$|_n_|_mask|metallic|occlusion|\blut\b|noise|"
    r"bumpmap|_m$|_ao$|sdf.?atlas|roughness|spec(?:ular)?)",
    re.I,
)
DROP = re.compile(r"(unity.?default|monoscript|dummytexture|unitybuiltin)", re.I)

# 先匹配的优先。用 bundle 名 + 容器路径 + 资源名一起判。
RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"font|fnt|ttf|otf|bitmapfont", re.I), "字体"),
    (re.compile(r"vfx|particle|\bfx[_/]|explosion|sparkle|trail", re.I), "特效"),
    (re.compile(r"splash|loading|logo|titleart", re.I), "加载"),
    (re.compile(r"frameatlas|_frames|avatarframe|headframe", re.I), "头像框"),
    (re.compile(r"avatar|portrait|profilepic", re.I), "头像"),
    (re.compile(r"mannequin|character|hero|npc|unit|spine", re.I), "角色"),
    (re.compile(r"costume|outfit|clothing|(?:^|/)sets/", re.I), "服装"),
    (re.compile(r"window|hud|popup|panel|\bui\b|/ui/|button|\bbtn", re.I), "界面"),
    (re.compile(r"offericon|iap|shop|gacha|礼包", re.I), "礼包"),
    (re.compile(r"reward|prize|loot", re.I), "奖励"),
    (re.compile(r"seasonpass|season|battlepass", re.I), "赛季"),
    (re.compile(r"clan|guild|alliance", re.I), "公会"),
    (re.compile(r"chapter|saga|episode|levelmap", re.I), "关卡"),
    (re.compile(r"propbundle|environment|tilemap|background|\bbg[_/]|scene", re.I), "场景"),
    (re.compile(r"item|booster|powerup|consumable|chest|egg", re.I), "道具"),
    (re.compile(r"emote|emoji|sticker", re.I), "表情"),
]


def drop_asset(name: str) -> bool:
    return bool(DROP.search(name or ""))


def is_tech(name: str) -> bool:
    return bool(TECH.search(name or ""))


def classify(bundle: str = "", container: str = "", asset: str = "") -> str:
    """返回顶层目录名。"""
    if drop_asset(asset) or drop_asset(bundle):
        return ""
    if is_tech(asset) or is_tech(Path(container or "").name):
        return "技术贴图"
    blob = " ".join(x for x in (bundle, container.replace("\\", "/"), asset) if x)
    for pat, bucket in RULES:
        if pat.search(blob):
            return bucket
    return "其他"


def classify_file(src: Path, container: str = "", asset: str = "") -> str:
    return classify(src.name, container, asset or src.stem)
