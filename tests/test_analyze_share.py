import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from gameaihack.cli import app
from gameaihack.ir import validate_ir
from gameaihack.share import is_forbidden


runner = CliRunner()


def test_analyze_and_share(unity_apk, tmp_path: Path):
    out = tmp_path / "jobs"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(unity_apk),
            "--out",
            str(out),
            "--i-have-rights",
            "--job-id",
            "t1",
        ],
    )
    assert result.exit_code == 0, result.output
    job = out / "t1"
    ir = json.loads((job / "raw" / "ir" / "game.ir.json").read_text(encoding="utf-8"))
    assert validate_ir(ir) == []
    assert (job / "raw" / "deliverable" / "COVER.md").exists()
    assert (job / "raw" / "deliverable" / "index.html").exists()
    assert "unity" in (job / "raw" / "deliverable" / "COVER.md").read_text(encoding="utf-8")
    assert (job / "output" / "策划" / "02-核心玩法.md").exists()
    assert (job / "output" / "美术" / "catalog.json").exists()
    assert "策划" in (job / "output" / "AGENTS.md").read_text(encoding="utf-8")

    # plant a forbidden file; share must skip it
    planted = job / "output" / "evil.so"
    planted.write_bytes(b"nope")
    zpath = tmp_path / "autopsy.zip"
    share = runner.invoke(app, ["share", str(job), "--to", str(zpath)])
    assert share.exit_code == 0, share.output
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
    assert any(n.endswith("index.html") for n in names)
    assert any("策划" in n or n.endswith("AGENTS.md") or n.endswith("玩法.md") for n in names)
    assert not any(n.endswith(".apk") or n.endswith(".so") for n in names)
    assert not any("/unpacked/" in n or "/extract/" in n for n in names)


def test_ir_validate_rejects_missing_radar(tmp_path: Path):
    bad = {
        "$schema": "gameaihack.gameir.v1",
        "job_id": "x",
        "package": {"name": "a"},
        "input_profile": {"score": 10, "warnings": []},
        "fingerprint": {"engine": "unknown"},
        "radar": [],
        "claims": [],
        "unknowns": [],
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    r = runner.invoke(app, ["ir-validate", str(p)])
    assert r.exit_code == 4


def test_forbidden_helpers():
    assert is_forbidden(Path("libil2cpp.so"))
    assert is_forbidden(Path("game.apk"))
    assert not is_forbidden(Path("COVER.md"))


def test_analyze_requires_rights_non_tty(unity_apk, tmp_path: Path):
    r = runner.invoke(
        app,
        ["analyze", str(unity_apk), "--out", str(tmp_path / "jobs")],
    )
    assert r.exit_code == 2
