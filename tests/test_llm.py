import json
from pathlib import Path

from gameaihack.ai_analyze import dsh_book_tasks, run_ai_analysis
from gameaihack.corpus import iter_source_files
from gameaihack.dsh_agent import DshError, _node_ok, dsh_argv, prepare_grok_home, require_dsh
from gameaihack.llm import LlmConfig, llm_enabled, resolve_llm


def test_resolve_llm_llm_bench_vars(monkeypatch):
    for k in (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "DEEPSEEK_BASE_URL",
        "LLM_MODELS",
        "LLM_MODEL",
        "DSH_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("LLM_MODELS", "grok-4.6")
    cfg = resolve_llm()
    assert cfg is not None
    assert cfg.api_key == "sk-test"
    assert cfg.model == "grok-4.6"
    assert cfg.chat_url == "http://127.0.0.1:8080/v1/chat/completions"
    assert cfg.openai_base == "http://127.0.0.1:8080/v1"


def test_chat_url_when_base_has_v1():
    cfg = LlmConfig(api_key="x", base_url="https://api.qnaigc.com/v1", model="m", source="t")
    assert cfg.chat_url == "https://api.qnaigc.com/v1/chat/completions"


def test_pytest_skips_llm_by_default():
    assert llm_enabled() is False


def test_ai_analyze_writes_index_without_key(tmp_path: Path):
    cfg_dir = tmp_path / "extract" / "normalized" / "configs"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "enemy.json").write_text('{"hp": 10}', encoding="utf-8")
    ir = {"package": {"name": "com.example.puzzle"}, "claims": [], "unknowns": [], "genre_guess": {}}
    result = run_ai_analysis(tmp_path, ir, cfg=None)
    assert result["files"] >= 1
    assert (tmp_path / "output" / "策划" / "ai" / "文件索引.md").exists()
    assert "enemy.json" in (tmp_path / "output" / "策划" / "ai" / "文件索引.md").read_text(encoding="utf-8")


def test_ai_analyze_mocked_chat(monkeypatch, tmp_path: Path):
    cfg_dir = tmp_path / "extract" / "normalized" / "configs"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "shop.json").write_text('[{"sku":"gold","price":6}]', encoding="utf-8")
    payload = {
        "summary": "合成加商店",
        "genre": "merge",
        "systems": [{"name": "商店", "detail": "有 sku", "path": "extract/normalized/configs/shop.json"}],
        "levels": "未见关卡表",
        "economy": "内购 gold",
        "unknowns": ["服务端价格"],
        "gdd_markdown": "# 经济\n有内购。",
    }

    def fake_chat(messages, **_k):
        assert messages[0]["role"] == "system"
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr("gameaihack.ai_analyze.chat", fake_chat)
    cfg = LlmConfig(api_key="sk", base_url="http://127.0.0.1:9", model="dummy", source="t")
    ir = {"package": {"name": "com.example.puzzle"}, "claims": [], "unknowns": [], "genre_guess": {"id": "merge"}}
    result = run_ai_analysis(tmp_path, ir, cfg=cfg)
    assert result["ok"]
    text = (tmp_path / "output" / "策划" / "ai" / "原始文件分析.md").read_text(encoding="utf-8")
    assert "合成加商店" in text
    assert any(c["id"] == "claim_ai_summary" for c in ir["claims"])


def test_dsh_book_tasks_read_raw_and_art(tmp_path: Path):
    art = tmp_path / "output" / "美术" / "角色"
    art.mkdir(parents=True)
    (art / "redbird.png").write_bytes(b"x")
    ir = {"package": {"name": "com.example.puzzle"}, "levels": [{"extra": {"chapter": 1}}]}
    tasks = dsh_book_tasks(tmp_path, ir)
    assert len(tasks) == 2
    titles = [t[0] for t in tasks]
    assert "全书策划" in titles
    assert "关卡策划" in titles
    blob = "\n".join(t[1] for t in tasks)
    assert "raw/" in blob
    assert "output/美术" in blob
    assert "output/策划" in blob
    assert "redbird.png" in blob


def test_output_dir_harvests_dsh(tmp_path: Path):
    from gameaihack.layout import output_dir
    from gameaihack.projects import harvest_dsh

    game = tmp_path / "game" / "策划"
    game.mkdir(parents=True)
    (game / "02-核心玩法.md").write_text("# DSH 终稿\n", encoding="utf-8")
    out = output_dir(tmp_path)
    assert out == tmp_path / "output"
    assert (out / "策划" / "02-核心玩法.md").read_text(encoding="utf-8") == "# DSH 终稿\n"
    assert not (tmp_path / "game").exists()
    leftover = tmp_path / "策划"
    leftover.mkdir()
    (leftover / "03-关卡设计.md").write_text("# 关卡\n", encoding="utf-8")
    n = harvest_dsh(tmp_path)
    assert n >= 1
    assert (out / "策划" / "03-关卡设计.md").exists()


def test_dsh_node_compat():
    assert _node_ok((22, 18, 0))
    assert _node_ok((24, 0, 0))
    assert not _node_ok((23, 5, 0))
    assert not _node_ok((20, 0, 0))


def test_dsh_argv_explicit(monkeypatch, tmp_path: Path):
    fake = tmp_path / "dsh"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("GAMEAIHACK_DSH", str(fake))
    assert dsh_argv() == [str(fake)]
    assert require_dsh() == [str(fake)]


def test_prepare_grok_home(tmp_path: Path):
    cfg = LlmConfig(
        api_key="sk-test",
        base_url="http://127.0.0.1:8080",
        model="grok-4.6",
        source="t",
    )
    patch = prepare_grok_home(tmp_path, cfg)
    text = patch.read_text(encoding="utf-8")
    assert "provider: grok" in text
    assert "grok-4.6" in text
    assert "compression: none" in text
    assert "root:" in text
    assert str((tmp_path / "sessions").resolve()) in text
    settings = (tmp_path / "settings.yaml").read_text(encoding="utf-8")
    assert "openai-completions" in settings
    assert "127.0.0.1:8080" in settings


def test_require_dsh_missing(monkeypatch):
    monkeypatch.delenv("GAMEAIHACK_DSH", raising=False)
    monkeypatch.setattr("gameaihack.dsh_agent.dsh_argv", lambda: None)
    try:
        require_dsh()
    except DshError as e:
        assert "必须" in str(e)
    else:
        raise AssertionError("expected DshError")


def test_iter_source_skips_ad_sdk(tmp_path: Path):
    root = tmp_path / "extract" / "normalized" / "configs"
    (root / "assets").mkdir(parents=True)
    (root / "res" / "mbridge").mkdir(parents=True)
    (root / "res" / "layout").mkdir(parents=True)
    (root / "assets" / "game.json").write_text('{"level":1,"hp":10}', encoding="utf-8")
    (root / "res" / "mbridge" / "ad.xml").write_text("<a/>", encoding="utf-8")
    (root / "res" / "layout" / "activity_main.xml").write_text("<LinearLayout/>", encoding="utf-8")
    (tmp_path / "ir").mkdir()
    (tmp_path / "ir" / "levels_index.json").write_text('[{"id":"chapter_001"}]', encoding="utf-8")
    files = iter_source_files(tmp_path)
    names = [p.name for p in files]
    assert "game.json" in names
    assert "levels_index.json" in names
    assert "ad.xml" not in names
    assert "activity_main.xml" not in names
