from pathlib import Path

from typer.testing import CliRunner

from gameaihack.cli import app
from tests.helpers import rich_game_files, write_zip

runner = CliRunner()


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

    ir = json.loads((out / "rsm" / "ir" / "game.ir.json").read_text(encoding="utf-8"))
    assert ir["resources"]
    assert ir["levels"]
    assert ir["claims"]
