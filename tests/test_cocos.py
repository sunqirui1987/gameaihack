from pathlib import Path

from gameaihack.extract.cocos import extract_cocos
from gameaihack.extract.xxtea import xxtea_encrypt


def test_cocos_xxtea_decrypt(tmp_path: Path):
    raw = b"local x = 1\nprint('ok')\n"
    key = b"secretkey1234"
    blob = b"SIGN" + xxtea_encrypt(raw, key)
    merged = tmp_path / "merged"
    (merged / "lib/arm64-v8a").mkdir(parents=True)
    (merged / "src").mkdir()
    (merged / "lib/arm64-v8a/libcocos2dlua.so").write_bytes(b"xxtea\x00secretkey1234\x00")
    (merged / "src/game.luac").write_bytes(blob)
    dest = tmp_path / "out"
    report = extract_cocos(merged, dest)
    assert report.extra.get("xxtea_key_found") is True
    assert any(it.kind == "script" for it in report.items)
    dumped = next((dest / "scripts").rglob("*.lua"))
    assert b"local x" in dumped.read_bytes()
