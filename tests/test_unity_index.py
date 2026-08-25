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
    assert "ch002_lv001" in ids
    ch2 = next(lv for lv in levels if lv["extra"]["chapter"] == 2)
    assert ch2["extra"]["level"] == 1
    assert ch2["extra"]["asset_level"] == 3
    assert ch2["name"] == "第2章第1关"
    assert any(lv.get("extra", {}).get("chapter") == 10 for lv in levels)
    assert all(lv["rebuild_grade"] == "L0" for lv in levels)
    shells = [lv for lv in levels if lv["id"].startswith("chapter_")]
    assert any(lv["extra"]["chapter"] == 10 for lv in shells)


def test_index_pairs_split_chapter_and_level_strings(tmp_path: Path):
    aa = tmp_path / "assets" / "aa"
    aa.mkdir(parents=True)
    blob = (
        b"Chapter001/Levelsxxxx"
        b"Level001.assetyyyy"
        b"Level002.assetzzzz"
        b"Chapter002/Levels"
        b"Level016.asset"
        b"Level017.asset"
        b"Chapter005/Levels"
        b"Chapter010/Levels"
        b"Level031.asset"
    )
    (aa / "catalog.bin").write_bytes(blob)
    levels = index_unity_levels(tmp_path)
    by: dict[int, list[dict]] = {}
    for lv in levels:
        by.setdefault(lv["extra"]["chapter"], []).append(lv)
    assert [x["extra"]["level"] for x in by[1]] == [1, 2]
    assert by[1][0]["name"] == "第1章第1关"
    assert len(by[2]) == 2
    assert by[2][0]["extra"]["level"] == 1
    assert by[2][0]["extra"]["asset_level"] == 16
    assert by[2][1]["extra"]["asset_level"] == 17
    assert by[2][0]["id"] == "ch002_lv001"
    assert len(by[5]) == 1
    assert "level" not in by[5][0]["extra"]
    assert by[10][0]["extra"]["level"] == 1
    assert by[10][0]["extra"]["asset_level"] == 31


def test_index_level_file_before_chapter_dir(tmp_path: Path):
    aa = tmp_path / "assets" / "aa"
    aa.mkdir(parents=True)
    (aa / "catalog.bin").write_bytes(b"Level001.assetxxxxChapter001/LevelsyLevel002.asset")
    levels = index_unity_levels(tmp_path)
    ch1 = [lv for lv in levels if lv["extra"]["chapter"] == 1]
    assets = [lv["extra"].get("asset_level") or lv["extra"]["level"] for lv in ch1]
    assert assets == [1, 2]
