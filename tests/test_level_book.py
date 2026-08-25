from pathlib import Path

from gameaihack.publish.level_book import (
    is_chapter_shell,
    tidy_design,
    write_level_book,
)


def test_level_book_is_human_readable(tmp_path: Path):
    ir = {
        "levels": [
            {"id": "ch001_lv001", "name": "Chapter 1 · Level 1", "extra": {"chapter": 1, "level": 1}},
            {"id": "ch001_lv002", "name": "Chapter 1 · Level 2", "extra": {"chapter": 1, "level": 2}},
            {"id": "ch001_lv003", "name": "Chapter 1 · Level 3", "extra": {"chapter": 1, "level": 3}},
            {"id": "ch002_lv001", "name": "Chapter 2 · Level 1", "extra": {"chapter": 2, "level": 1}},
            {"id": "ch003_lv001", "name": "Chapter 3 · Level 1", "extra": {"chapter": 3, "level": 1}},
            {"id": "chapter_005", "name": "Chapter 5", "extra": {"chapter": 5}},
            {"id": "ch093_lv001", "name": "Chapter 93 · Level 1", "extra": {"chapter": 93, "level": 1}},
            {"id": "ch093_lv040", "name": "Chapter 93 · Level 40", "extra": {"chapter": 93, "level": 40}},
        ]
    }
    dest = tmp_path / "关卡"
    write_level_book(dest, ir, title="测试游戏")
    readme = (dest / "README.md").read_text(encoding="utf-8")
    assert "第 1 章" in readme
    assert "第 2～3 章" in readme
    assert "每章 1 关" in readme
    assert "关数未知" in readme
    assert "原资源名" not in readme
    assert "ch005_lv001" not in readme

    ch1 = (dest / "第001章.md").read_text(encoding="utf-8")
    assert "# 第 1 章" in ch1
    assert "| 关 | 这一关干什么 | 通关后 |" in ch1
    assert "第 1 关" in ch1
    assert "全游戏第一局" in ch1
    assert "第 3 关" in ch1
    assert "ch001_lv001" not in ch1
    assert "原资源名" not in ch1
    assert "摆法未知" not in ch1

    ch5 = (dest / "第005章.md").read_text(encoding="utf-8")
    assert "关数" in ch5 or "有几关" in ch5
    assert "未知" in ch5
    assert "ch005_lv001" not in ch5
    assert "占位关" not in ch5
    assert "原资源名" not in ch5
    assert "第 1 关" in ch5
    assert "重做" in ch5

    ch93 = (dest / "第093章.md").read_text(encoding="utf-8")
    assert "第 1 关" in ch93
    assert "ch093_lv001" not in ch93


def test_chapter_shell_detection():
    assert is_chapter_shell([{"id": "chapter_005", "extra": {"chapter": 5}}])
    assert not is_chapter_shell([{"id": "ch001_lv001", "extra": {"chapter": 1, "level": 1}}])


def test_tidy_design_drops_stub_files(tmp_path: Path):
    dest = tmp_path / "策划"
    dest.mkdir()
    (dest / "03-关卡.md").write_text("# 已迁移\n\n见 03-关卡设计.md\n", encoding="utf-8")
    (dest / "02-核心玩法.md").write_text("# 核心玩法\n真正的正文\n", encoding="utf-8")
    (dest / "_w.py").write_text("print(1)\n", encoding="utf-8")
    tidy_design(dest)
    assert not (dest / "03-关卡.md").exists()
    assert not (dest / "_w.py").exists()
    assert (dest / "02-核心玩法.md").exists()


def test_level_book_merges_catalog_over_chapter_shell(tmp_path: Path):
    job = tmp_path
    merged = job / "raw" / "unpacked" / "merged" / "assets" / "aa"
    merged.mkdir(parents=True)
    (merged / "catalog.bin").write_bytes(
        b"Chapter001/LevelsxxxxLevel001.assetyyyyLevel002.assetzzzzChapter005/Levels"
    )
    ir = {
        "levels": [
            {"id": "chapter_001", "name": "Chapter 1", "extra": {"chapter": 1}},
            {"id": "chapter_005", "name": "Chapter 5", "extra": {"chapter": 5}},
        ]
    }
    dest = tmp_path / "output" / "策划" / "关卡"
    write_level_book(dest, ir, job_dir=job)
    ch1 = (dest / "第001章.md").read_text(encoding="utf-8")
    assert "2 关" in ch1 or "第 2 关" in ch1
    assert "只看到" not in ch1
    ch5 = (dest / "第005章.md").read_text(encoding="utf-8")
    assert "未知" in ch5
