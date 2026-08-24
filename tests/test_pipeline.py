import json
from pathlib import Path

from typer.testing import CliRunner

from gameaihack.cli import app
from gameaihack.content.ir import validate_ir
from tests.helpers import rich_game_files, write_zip

runner = CliRunner()


def test_full_pipeline_rich_apk(tmp_path: Path):
    apk = write_zip(tmp_path / "rich.apk", rich_game_files(tmp_path))
    out = tmp_path / "jobs"
    r = runner.invoke(
        app,
        ["analyze", str(apk), "--out", str(out), "--i-have-rights", "--job-id", "rich1"],
    )
    assert r.exit_code == 0, r.output
    job = out / "rich1"
    ir = json.loads((job / "raw" / "ir" / "game.ir.json").read_text(encoding="utf-8"))
    assert validate_ir(ir) == []
    kinds = {x["kind"] for x in ir["resources"]}
    assert "texture" in kinds
    assert "config" in kinds
    roles = {t["role"] for t in ir["tables"]}
    assert "enemy" in roles
    assert "shop" in roles or "iap" in roles
    grades = {lv["rebuild_grade"] for lv in ir["levels"]}
    assert "L2" in grades or "L3" in grades
    ids = {c["id"] for c in ir["claims"]}
    assert "claim_ads" in ids
    assert "claim_levels" in ids
    assert (job / "raw" / "deliverable" / "design" / "06-经济与商业化.md").exists()
    assert (job / "raw" / "deliverable" / "tables" / "index.csv").exists()
    assert (job / "output" / "AGENTS.md").exists()
    assert (job / "output" / "策划" / "02-核心玩法.md").exists()
    assert (job / "output" / "策划" / "00-封面.md").exists()
    assert (job / "output" / "策划" / "关卡" / "README.md").exists()
    assert (job / "output" / "策划" / "ai" / "文件索引.md").exists()
    assert (job / "output" / "data" / "game.ir.json").exists()
    assert (job / "output" / "data" / "levels" / "index.csv").exists()
    assert not list((job / "output" / "data" / "levels").glob("ch*.json"))
    assert (job / "output" / "美术" / "catalog.md").exists()
    assert list((job / "output" / "美术" / "textures").rglob("*"))
    html = (job / "raw" / "deliverable" / "index.html").read_text(encoding="utf-8")
    assert "完整度雷达" in html
    assert ir["genre_guess"]["id"] in {"puzzle", "rpg"}
    l2 = [lv for lv in ir["levels"] if str(lv.get("rebuild_grade", "L0")) >= "L2"]
    assert len(l2) >= 10
    claim_ids = {c["id"] for c in ir["claims"]}
    assert "claim_loc" in claim_ids
    assert "claim_ftue" in claim_ids
    assert (job / "raw" / "deliverable" / "levels" / "gallery.html").exists()
    thumbs = list((job / "raw" / "deliverable" / "assets" / "thumbs").glob("*"))
    assert thumbs
    zpath = tmp_path / "autopsy.zip"
    sh = runner.invoke(app, ["share", str(job), "--to", str(zpath)])
    assert sh.exit_code == 0, sh.output
