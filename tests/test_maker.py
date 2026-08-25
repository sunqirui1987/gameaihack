from pathlib import Path

from gameaihack.publish.maker import emit_maker_project


def test_emit_maker_writes_output_tree(tmp_path: Path):
    job = tmp_path / "job"
    (job / "output" / "策划").mkdir(parents=True)
    (job / "output" / "策划" / "02-核心玩法.md").write_text("# 玩法\n", encoding="utf-8")
    result = emit_maker_project(job, {"package": {"name": "com.example.g"}}, run_init=False)
    out = job / "output"
    assert Path(result["path"]) == out
    assert (out / "scripts" / "main.lua").is_file()
    assert (out / "assets" / "image").is_dir()
    agents = (out / "AGENTS.md").read_text(encoding="utf-8")
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "TapTap Maker" in agents
    assert "策划/02-核心玩法.md" in agents
    assert "npx -y @taptap/maker install --ide codex,cursor,claude" in readme
    assert "npx -y @taptap/maker init" in readme
    assert not (job / "maker").exists()
    lua = (out / "scripts" / "main.lua").read_text(encoding="utf-8")
    assert "os.clock" not in lua or "不要用 os.clock" in lua


def test_reset_keeps_maker_engine_dirs(tmp_path: Path):
    from gameaihack.core.layout import reset_output

    out = tmp_path / "output"
    (out / "策划").mkdir(parents=True)
    (out / "策划" / "stale.md").write_text("old", encoding="utf-8")
    (out / "美术").mkdir(parents=True)
    (out / "美术" / "a.png").write_bytes(b"x")
    (out / "engine-docs").mkdir(parents=True)
    (out / "engine-docs" / "index.md").write_text("keep", encoding="utf-8")
    (out / "scripts").mkdir(parents=True)
    (out / "scripts" / "main.lua").write_text("-- keep\n", encoding="utf-8")
    reset_output(tmp_path)
    assert not (out / "策划" / "stale.md").exists()
    assert (out / "美术" / "a.png").exists()
    assert (out / "engine-docs" / "index.md").exists()
    assert (out / "scripts" / "main.lua").exists()
