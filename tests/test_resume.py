from pathlib import Path

from typer.testing import CliRunner

from gameaihack.cli import app
from tests.helpers import rich_game_files, write_zip

runner = CliRunner()


def test_rerun_skips_raw_and_clears_design(tmp_path: Path):
    apk = write_zip(tmp_path / "r.apk", rich_game_files(tmp_path))
    out = tmp_path / "jobs"
    args = ["analyze", str(apk), "--out", str(out), "--i-have-rights", "--job-id", "keep"]
    r1 = runner.invoke(app, args)
    assert r1.exit_code == 0, r1.output
    job = out / "keep"
    marker = job / "raw" / "unpacked" / "merged" / "_keep.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("keep-raw", encoding="utf-8")
    stale = job / "output" / "策划" / "stale.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("old", encoding="utf-8")
    art = job / "output" / "美术"
    art.mkdir(parents=True, exist_ok=True)
    keep_png = art / "keep.png"
    keep_png.write_bytes(b"png")
    r2 = runner.invoke(app, args)
    assert r2.exit_code == 0, r2.output
    assert marker.read_text(encoding="utf-8") == "keep-raw"
    assert not stale.exists()
    assert keep_png.exists()


def test_from_stage_design_keeps_resources(tmp_path: Path):
    apk = write_zip(tmp_path / "r.apk", rich_game_files(tmp_path))
    out = tmp_path / "jobs"
    r1 = runner.invoke(
        app,
        ["analyze", str(apk), "--out", str(out), "--i-have-rights", "--job-id", "rsm"],
    )
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(
        app,
        [
            "analyze",
            str(apk),
            "--out",
            str(out),
            "--i-have-rights",
            "--job-id",
            "rsm",
            "--from-stage",
            "design",
        ],
    )
    assert r2.exit_code == 0, r2.output
    import json

    ir = json.loads((out / "rsm" / "raw" / "ir" / "game.ir.json").read_text(encoding="utf-8"))
    assert ir["resources"]
    assert ir["levels"]
    assert ir["claims"]
