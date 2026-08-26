"""反编译贴图：按 Maker 里怎么用分类，不按运营活动分类。"""

from __future__ import annotations

import re
from pathlib import Path

TECH = re.compile(
    r"(normalmap|_n$|_n_|_mask|metallic|occlusion|\blut\b|noise|"
    r"bumpmap|_m$|_ao$|sdf.?atlas|roughness|spec(?:ular)?)",
    re.I,
)
DROP = re.compile(
    r"(unity.?default|monoscript|dummytexture|unitybuiltin)",
    re.I,
)
# 运营/商业化贴图不进 Maker 工程
SKIP = re.compile(
    r"(iap|gacha|offericon|seasonpass|battlepass|shop_pack|"
    r"clan|guild|alliance|avatarframe|headframe|portraitframe|"
    r"礼包|通行证)",
    re.I,
)

# Maker 用的桶：sprites 场上角色/抛体，world 地形障碍，ui 局内 HUD，fx 特效
RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"vfx|particle|\bfx[_/]|explosion|sparkle|trail|blast", re.I), "fx"),
    (re.compile(r"_ui_|/ui/|(?:^|/)ui[_-]|button|\bbtn|hud|window|popup|panel", re.I), "ui"),
    (
        re.compile(
            r"tilemap|background|\bbg[_/]|terrain|ground|block|wood|stone|"
            r"propbundle|environment|scene|obstacle|plank|glass",
            re.I,
        ),
        "world",
    ),
    (
        re.compile(
            r"character|hero|npc|unit|spine|sprite|sling|bird|pig|"
            r"projectile|ammo|enemy|player|mannequin",
            re.I,
        ),
        "sprites",
    ),
]


def drop_asset(name: str) -> bool:
    return bool(DROP.search(name or "") or SKIP.search(name or ""))


def is_tech(name: str) -> bool:
    return bool(TECH.search(name or ""))


def classify(bundle: str = "", container: str = "", asset: str = "") -> str:
    """返回 Maker 资源桶。空字符串 = 不要进工程。"""
    if drop_asset(asset) or drop_asset(bundle) or drop_asset(container):
        return ""
    if is_tech(asset) or is_tech(Path(container or "").name):
        return ""
    blob = " ".join(x for x in (bundle, container.replace("\\", "/"), asset) if x)
    if SKIP.search(blob):
        return ""
    for pat, bucket in RULES:
        if pat.search(blob):
            return bucket
    return "sprites"


def classify_file(src: Path, container: str = "", asset: str = "") -> str:
    return classify(src.name, container, asset or src.stem)
