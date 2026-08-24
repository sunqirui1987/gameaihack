from pathlib import Path

from gameaihack.content.unity_index import index_unity_levels


def test_index_chapters_from_catalog(tmp_path: Path):
    aa = tmp_path / "assets" / "aa"
    aa.mkdir(parents=True)
    blob = (
        b"xxxxChapter001/Levels/Level001.assetxxxx"
        b"Assets\\Content\\Saga\\Chapters\\Chapter002\\Levels\\Level003.assetyyyy"
        b"Chapter010/Levels"
    )
    (aa / "catalog.bin").write_bytes(blob)
    levels = index_unity_levels(tmp_path)
    ids = {lv["id"] for lv in levels}
    assert "ch001_lv001" in ids
    assert "ch002_lv003" in ids
    assert any(lv.get("extra", {}).get("chapter") == 10 for lv in levels)
    assert all(lv["rebuild_grade"] == "L0" for lv in levels)
