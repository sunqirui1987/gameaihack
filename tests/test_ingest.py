from pathlib import Path

from tests.helpers import unity_apk_files, write_zip
from gameaihack.ingest import logical_paths, unpack_to


def test_xapk_merges_apks_and_obb(tmp_path: Path):
    base = write_zip(tmp_path / "base.apk", unity_apk_files(with_data=True))
    split = write_zip(
        tmp_path / "config.arm64.apk",
        {"lib/arm64-v8a/libunity.so": b"u"},
    )
    obb = write_zip(tmp_path / "main.obb", {"assets/extra.txt": b"hello"})
    xapk = tmp_path / "game.xapk"
    write_zip(
        xapk,
        {
            "manifest.json": b'{"package_name":"com.example.game"}',
            "com.example.game.apk": base.read_bytes(),
            "config.arm64.apk": split.read_bytes(),
            "main.1.com.example.game.obb": obb.read_bytes(),
        },
    )
    paths, meta, pkg = logical_paths(xapk)
    assert meta.kind == "xapk"
    assert any(p.endswith("data.unity3d") for p in paths)
    assert any(p.endswith("libunity.so") for p in paths)
    assert any(p.endswith("extra.txt") for p in paths)
    assert pkg.name == "com.example.game"

    dest = tmp_path / "unpacked"
    unpack_to(xapk, dest)
    merged = dest / "merged"
    assert (merged / "assets/bin/Data/data.unity3d").exists()
    assert (merged / "assets/extra.txt").read_text() == "hello"
