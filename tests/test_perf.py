from pathlib import Path

from gameaihack.art.png import MIN_PNG, write_rgba_png
from gameaihack.art.unity import (
    STAMP_VER,
    _collect_files,
    _load_stamp,
    _out_from_container,
    _save_stamp,
    _src_sig,
    _stamp_key,
)
from gameaihack.core.fs import (
    count_by_suffix,
    iter_files,
    link_or_copy,
    rel_files,
    sha256_reuse,
    so_files,
)
from gameaihack.extract import run_extract
from gameaihack.extract.stringsutil import strings_from_file
from gameaihack.ingest.unpack import walk_files


def test_iter_ascii_strings_finds_xxtea(tmp_path: Path):
    p = tmp_path / "lib.so"
    p.write_bytes(b"\x00" * 4096 + b"xxtea\x00secretkey1234\x00libil2cpp")
    found = strings_from_file(p)
    assert "xxtea" in found
    assert "secretkey1234" in found
    assert "libil2cpp" in found


def test_walk_files_matches_tree(tmp_path: Path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "c.txt").write_text("x")
    (tmp_path / "z.bin").write_bytes(b"1")
    got = walk_files(tmp_path)
    assert got == ["a/b/c.txt", "z.bin"]
    assert rel_files(tmp_path) == got
    assert {p.name for p in iter_files(tmp_path)} == {"c.txt", "z.bin"}


def test_link_or_copy_same_bytes(tmp_path: Path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello-hardlink")
    dest = tmp_path / "sub" / "dest.bin"
    link_or_copy(src, dest)
    assert dest.read_bytes() == b"hello-hardlink"
    try:
        assert src.stat().st_ino == dest.stat().st_ino
    except AssertionError:
        pass
    dest2 = tmp_path / "sub" / "dest.bin"
    src.write_bytes(b"hello-hardlink")
    link_or_copy(src, dest2)
    assert dest2.read_bytes() == b"hello-hardlink"


def test_sha256_reuse_skips_reread(tmp_path: Path):
    p = tmp_path / "pack.apk"
    p.write_bytes(b"abc" * 100)
    first, meta = sha256_reuse(p, None)
    assert len(first) == 64
    again, meta2 = sha256_reuse(p, {**meta, "sha256": first})
    assert again == first
    assert meta2["sha256"] == first
    p.write_bytes(b"xyz" * 200)
    changed, _ = sha256_reuse(p, meta2)
    assert changed != first


def test_so_files_prefers_arm64(tmp_path: Path):
    arm64 = tmp_path / "lib" / "arm64-v8a"
    arm64.mkdir(parents=True)
    (arm64 / "libil2cpp.so").write_bytes(b"\x7fELF")
    (arm64 / "libc++.so").write_bytes(b"\x7fELF")
    v7 = tmp_path / "lib" / "armeabi-v7a"
    v7.mkdir(parents=True)
    (v7 / "libil2cpp.so").write_bytes(b"v7")
    got = so_files(tmp_path)
    assert got == [arm64 / "libil2cpp.so"]


def test_run_extract_skips_unreal_on_unity(tmp_path: Path):
    merged = tmp_path / "merged"
    (merged / "assets" / "bin" / "Data").mkdir(parents=True)
    (merged / "assets" / "bin" / "Data" / "data.unity3d").write_bytes(b"UNTY")
    (merged / "Foo.pak").write_bytes(b"not-a-real-pak")
    (merged / "assets" / "x.json").write_text('{"a":1}')
    dest = tmp_path / "out"
    report = run_extract(merged, dest, {"engine": "unity"})
    assert "unreal" not in report.extra
    assert "godot" not in report.extra
    assert "cocos" not in report.extra


def test_art_stamp_roundtrip(tmp_path: Path):
    dest = tmp_path / "美术"
    dest.mkdir()
    src = tmp_path / "foo.bundle"
    src.write_bytes(b"bundle")
    stamp = {"v": STAMP_VER, "files": {_stamp_key(src): {**_src_sig(src), "added": 3}}}
    _save_stamp(dest, stamp)
    loaded = _load_stamp(dest)
    assert loaded["v"] == STAMP_VER
    rec = loaded["files"][_stamp_key(src)]
    assert rec["added"] == 3
    assert rec["size"] == src.stat().st_size


def test_collect_files_aa_and_data(tmp_path: Path):
    merged = tmp_path / "merged"
    aa = merged / "assets" / "aa" / "Android"
    aa.mkdir(parents=True)
    (aa / "avatars_android.bundle").write_bytes(b"x" * 300)
    data = merged / "assets" / "bin" / "Data"
    data.mkdir(parents=True)
    (data / "datapack.unity3d").write_bytes(b"y" * 300)
    files = _collect_files(merged)
    names = {p.name for p in files}
    assert "avatars_android.bundle" in names
    assert "datapack.unity3d" in names


def test_write_png_magic(tmp_path: Path):
    p = tmp_path / "a.png"
    write_rgba_png(p, 2, 2, bytes([255, 0, 0, 255] * 4))
    assert p.read_bytes()[:8] == MIN_PNG[:8]


def test_so_files_skips_uninteresting_abi(tmp_path: Path):
    arm64 = tmp_path / "lib" / "arm64-v8a"
    arm64.mkdir(parents=True)
    (arm64 / "libc++.so").write_bytes(b"\x7fELF")
    v7 = tmp_path / "lib" / "armeabi-v7a"
    v7.mkdir(parents=True)
    (v7 / "libil2cpp.so").write_bytes(b"v7")
    assert so_files(tmp_path) == [v7 / "libil2cpp.so"]


def test_long_ascii_run_keeps_key(tmp_path: Path):
    p = tmp_path / "lib.so"
    p.write_bytes(b"A" * 300 + b"secretkey1234")
    found = strings_from_file(p)
    assert any("secretkey1234" in s for s in found)


def test_classify_buckets():
    from gameaihack.art.classify import classify

    assert classify("avatars_android.bundle", "", "x") == "头像"
    assert classify("costume", "assets/content/sets/Witch/x.png", "x") == "服装"
    assert classify("ui", "assets/ui/window/shop.png", "shop") == "界面"
    assert classify("x", "assets/content/sets/Witch/a.png", "a") == "服装"
    assert classify("fx", "assets/vfx/hit.png", "hit") == "特效"
    assert classify("x", "t.png", "hero_n") == "技术贴图"
    assert classify("misc", "foo.png", "foo") == "其他"
    assert classify("", "", "01_UI_HatShop_HatSetButton.png") == "界面"


def test_art_manifest_lists(tmp_path: Path):
    from gameaihack.art.manifest import write_manifest
    from gameaihack.art.png import write_rgba_png

    art = tmp_path / "美术"
    (art / "角色").mkdir(parents=True)
    write_rgba_png(art / "角色" / "hero.png", 2, 2, bytes([255, 0, 0, 255] * 4))
    snap = write_manifest(art, {"package": {"name": "com.example.puzzle"}})
    assert snap["total"] == 1
    assert (art / "清单" / "总览.md").is_file()
    assert (art / "清单" / "程序.md").is_file()
    assert (art / "清单" / "美术.md").is_file()
    assert (art / "清单" / "全部.csv").is_file()
    write_rgba_png(art / "角色" / "01_UI_HatShop.png", 2, 2, bytes([0, 255, 0, 255] * 4))
    write_rgba_png(art / "角色" / "RedBird.png", 64, 64, bytes([255, 0, 0, 255] * 4096))
    write_manifest(art, {"package": {"name": "com.example.puzzle"}})
    digest = (art / "清单" / "给策划.md").read_text(encoding="utf-8")
    assert "RedBird.png" in digest
    if "01_UI_HatShop.png" in digest:
        assert digest.index("RedBird.png") < digest.index("01_UI_HatShop.png")
    assert (art / "清单" / "给策划.md").is_file()
    text = (art / "清单" / "总览.md").read_text(encoding="utf-8")
    assert "角色" in text
    assert "程序" in text
    assert "角色" in (art / "清单" / "给策划.md").read_text(encoding="utf-8")


def test_fact_source_combines_raw_and_art(tmp_path: Path):
    from gameaihack.art.png import write_rgba_png
    from gameaihack.content.facts import write_fact_source

    art = tmp_path / "output" / "美术" / "界面"
    art.mkdir(parents=True)
    write_rgba_png(art / "hud.png", 2, 2, bytes([0, 255, 0, 255] * 4))
    ir = {
        "package": {"name": "com.example.puzzle"},
        "fingerprint": {"engine": "unity"},
        "levels": [{"id": "1", "extra": {"chapter": 1}}],
        "tables": [{"id": "shop", "role": "shop", "row_count": 3}],
        "claims": [{"text": "有商店表"}],
    }
    dest = write_fact_source(tmp_path, ir)
    text = dest.read_text(encoding="utf-8")
    assert "事实源" in text
    assert "界面" in text
    assert "shop" in text
    assert (tmp_path / "raw" / "清单" / "给策划.md").is_file()
    assert (tmp_path / "output" / "策划" / "图鉴" / "README.md").is_file()
    assert (tmp_path / "清单.md").is_file()
    assert "总清单" in (tmp_path / "清单.md").read_text(encoding="utf-8") or "清单" in (
        tmp_path / "清单.md"
    ).read_text(encoding="utf-8")


def test_out_from_container_keeps_set_name(tmp_path: Path):
    out = _out_from_container(
        tmp_path,
        "服装",
        "assets/content/sets/Witch/mannequins/final/RedBird.png",
        "RedBird",
    )
    assert out == tmp_path / "服装" / "Witch" / "RedBird.png"


def test_inspect_kit_without_art(tmp_path: Path):
    from gameaihack.publish.kit import inspect_kit

    snap = inspect_kit(tmp_path, {"levels": []})
    assert snap["art"]["png"] == 0
    assert snap["art"]["folders"] == []


def test_loc_ignores_agent_in_path(tmp_path: Path):
    from gameaihack.content.loc import extract_loc

    merged = tmp_path / "merged"
    (merged / "assets").mkdir(parents=True)
    (merged / "assets" / "config.json").write_text('{"a":"1","b":"2","c":"3"}', encoding="utf-8")
    (merged / "assets" / "i18n").mkdir()
    (merged / "assets" / "i18n" / "zh.json").write_text(
        '{"ui_start":"开始","ui_fail":"失败","shop_title":"商店"}', encoding="utf-8"
    )
    loc = extract_loc(tmp_path / "missing", merged, [])
    assert "zh" in loc["languages"]
    assert any(s.get("key") == "ui_start" for s in loc["samples"])


def test_count_by_suffix_skips_dotfiles(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.png").write_bytes(b"1")
    (tmp_path / "a" / ".rip.json").write_text("{}")
    (tmp_path / ".hidden.png").write_bytes(b"2")
    assert count_by_suffix(tmp_path, ".png") == 1
