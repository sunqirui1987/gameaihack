from __future__ import annotations

import json
import zipfile
from pathlib import Path

from gameaihack.art.png import write_rgba_png


def write_zip(path: Path, files: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def unity_apk_files(*, with_data: bool = True) -> dict[str, bytes]:
    files = {
        "lib/arm64-v8a/libil2cpp.so": b"\x7fELF-fake",
        "AndroidManifest.xml": b'<?xml version="1.0"?><manifest package="com.example.puzzle" android:versionName="1.0" android:versionCode="1"/>',
    }
    if with_data:
        files["assets/bin/Data/data.unity3d"] = b"UNTY"
        files["assets/bin/Data/global-metadata.dat"] = b"meta"
    return files


def _png(tmp: Path) -> bytes:
    p = tmp / "_px.png"
    write_rgba_png(p, 2, 2, bytes([255, 0, 0, 255] * 4))
    return p.read_bytes()


def rich_game_files(tmp: Path) -> dict[str, bytes]:
    png = _png(tmp)
    enemy = b"""[
      {"id":1,"name":"slime","hp":30,"atk":5},
      {"id":2,"name":"bat","hp":20,"atk":8}
    ]"""
    shop = b"""[
      {"id":"gold_100","price":6,"sku":"com.example.gold100"},
      {"id":"stamina_refill","price":3,"sku":"com.example.stamina"}
    ]"""
    loc = '{"ui_start":"开始","ui_fail":"失败了","shop_title":"商店","ad_reward":"看完广告领取"}'.encode("utf-8")
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
  local stamina = 120
  CameraShake()
  attack()
  jump()
end
"""
    so = b"\x7fELF" + b"\x00" * 32 + b"xxtea\x00secretkey1234\x00libil2cpp"
    return {
        "lib/arm64-v8a/libil2cpp.so": so,
        "AndroidManifest.xml": b'<?xml version="1.0"?><manifest package="com.example.puzzle" android:versionName="1.0" android:versionCode="1"/>',
        "assets/bin/Data/data.unity3d": b"UNTY",
        "assets/bin/Data/global-metadata.dat": b"meta",
        "assets/textures/slime.png": png,
        "assets/audio/bgm.ogg": b"OggS-fake",
        "assets/config/enemy.json": enemy,
        "assets/config/shop.json": shop,
        **files_levels,
        "assets/i18n/zh.json": loc,
        "assets/maps/forest.tmx": tmx,
        "assets/src/app.lua": lua,
    }
