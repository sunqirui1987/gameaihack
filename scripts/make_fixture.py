#!/usr/bin/env python3
"""生成自制最小 APK（不含商业包），默认写到 samples/golden.apk。"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameaihack.art.png import write_rgba_png  # noqa: E402


def write_zip(path: Path, files: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def _png() -> bytes:
    p = ROOT / "samples" / "_px.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    write_rgba_png(p, 2, 2, bytes([255, 0, 0, 255] * 4))
    return p.read_bytes()


def golden_files() -> dict[str, bytes]:
    png = _png()
    enemy = json.dumps(
        [{"id": 1, "name": "slime", "hp": 30, "atk": 5}, {"id": 2, "name": "bat", "hp": 20, "atk": 8}]
    ).encode()
    shop = json.dumps(
        [
            {"id": "gold_100", "price": 6, "sku": "com.example.gold100"},
            {"id": "stamina_refill", "price": 3, "sku": "com.example.stamina"},
        ]
    ).encode()
    loc = '{"ui_start":"开始","ui_fail":"失败了","shop_title":"商店","ad_reward":"看完广告领取"}'.encode()
    files_levels = {}
    for i in range(1, 11):
        board = [[(i + x + y) % 4 for x in range(4)] for y in range(4)]
        files_levels[f"assets/levels/level_{i:03d}.json"] = json.dumps(
            {"id": f"stage_{i:03d}", "moves": 22 - i, "win": "clear", "board": board}
        ).encode()
    tmx = b"""<?xml version="1.0"?>
<map width="4" height="2">
  <layer name="g" width="4" height="2">
    <data encoding="csv">1,0,2,0,3,1,0,2</data>
  </layer>
</map>
"""
    lua = b"""
local function play()
  ShowRewardVideo()
  Track("level_fail")
  Track("iap_click")
end
"""
    so = b"\x7fELF" + b"\x00" * 32 + b"xxtea\x00secretkey1234\x00libil2cpp"
    return {
        "lib/arm64-v8a/libil2cpp.so": so,
        "AndroidManifest.xml": (
            b'<?xml version="1.0"?><manifest package="com.example.puzzle" '
            b'android:versionName="1.0" android:versionCode="1"/>'
        ),
        "assets/bin/Data/data.unity3d": b"UNTY",
        "assets/bin/Data/global-metadata.dat": b"meta",
        "assets/textures/slime.png": png,
        "assets/audio/bgm.ogg": b"OggS-fake",
        "assets/config/enemy.json": enemy,
        "assets/config/shop.json": shop,
        "assets/loc/zh.json": loc,
        "assets/maps/demo.tmx": tmx,
        "assets/scripts/play.lua": lua,
        **files_levels,
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "samples" / "golden.apk"
    write_zip(out, golden_files())
    print(out)


if __name__ == "__main__":
    main()
