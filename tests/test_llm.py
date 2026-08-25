import json
from pathlib import Path

from gameaihack.agent.book import book_tasks, dsh_book_tasks, run_ai_analysis
from gameaihack.agent.corpus import iter_source_files
from gameaihack.agent.dsh import DshError, _node_ok, dsh_argv, prepare_grok_home, require_dsh
from gameaihack.agent.llm import LlmConfig, llm_enabled, resolve_llm


def test_bind_file_writes_run_log(tmp_path: Path):
    from gameaihack.core.progress import bind_file, log, unbind

    path = tmp_path / "run.log"
    tok = bind_file(path)
    try:
        log("hello-log")
    finally:
        unbind(tok)
    text = path.read_text(encoding="utf-8")
    assert "hello-log" in text


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
    assert "只读" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "output/策划" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
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

    monkeypatch.setattr("gameaihack.agent.book.chat", fake_chat)
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
    tasks = book_tasks(tmp_path, ir)
    assert tasks == dsh_book_tasks(tmp_path, ir)
    assert len(tasks) == 3
    titles = [t[0] for t in tasks]
    assert "核心玩法" in titles
    assert "系统全书" in titles
    assert "关卡与图鉴" in titles
    blob = "\n".join(t[1] for t in tasks)
    assert "raw/" in blob
    assert "output/美术" in blob
    assert "output/策划" in blob
    assert "事实源" in blob
    assert "核心玩法" in blob
    assert "制作顺序.md" in blob
    assert "第一局" in blob
    assert "图鉴" in blob
    assert "redbird.png" in blob
    assert (tmp_path / "output" / "策划" / "_事实源.md").is_file()
    assert (tmp_path / "raw" / "清单" / "给策划.md").is_file()
    assert (tmp_path / "output" / "美术" / "清单" / "给策划.md").is_file()


def test_parse_via_grok_codex_dsh():
    from gameaihack.agent.drivers import AgentError, parse_via, resolve_driver
    from gameaihack.agent.drivers.dsh import DshDriver
    from gameaihack.agent.drivers.grok import GrokDriver, grok_argv
    from gameaihack.agent.drivers.codex import CodexDriver

    assert parse_via("grok") == "grok"
    assert parse_via("codex-cli") == "codex"
    assert parse_via("deepseek") == "dsh"
    try:
        parse_via("http")
    except AgentError:
        pass
    else:
        raise AssertionError("http 不应是合法通道")
    assert isinstance(resolve_driver("grok"), GrokDriver)
    assert isinstance(resolve_driver("codex"), CodexDriver)
    assert isinstance(resolve_driver("dsh"), DshDriver)
    argv = grok_argv(
        binary="grok",
        model="grok-4.6",
        effort="xhigh",
        prompt_file="/tmp/p.txt",
        cwd="/tmp/job",
    )
    joined = " ".join(argv)
    assert "--cwd /tmp/job" in joined
    assert "--prompt-file /tmp/p.txt" in joined
    assert "--always-approve" in joined
    assert "--effort" in argv and "xhigh" in argv
    from gameaihack.agent.drivers.codex import CodexDriver, codex_argv

    cargv = codex_argv(binary="codex", model="gpt-5", cwd="/tmp/job")
    cjoin = " ".join(cargv)
    assert "model_reasoning_effort=" in cjoin
    assert "xhigh" in cjoin


def test_reset_output_keeps_art(tmp_path: Path):
    from gameaihack.core.layout import reset_output

    out = tmp_path / "output"
    (out / "策划").mkdir(parents=True)
    (out / "美术").mkdir(parents=True)
    (out / "策划" / "stale.md").write_text("old", encoding="utf-8")
    (out / "美术" / "a.png").write_bytes(b"x")
    (out / "复刻说明.md").write_text("old", encoding="utf-8")
    reset_output(tmp_path)
    assert not (out / "策划" / "stale.md").exists()
    assert (out / "美术" / "a.png").exists()
    assert not (out / "复刻说明.md").exists()
    assert (out / "策划").is_dir()


def test_is_retryable_concurrency():
    from gameaihack.agent.drivers import is_retryable

    assert is_retryable("PI_AI_ERROR: Concurrency limit exceeded for account, please retry later")
    assert is_retryable("HTTP 429 rate limit")
    assert not is_retryable("file not found")


def test_seal_kit_writes_remake_guide(tmp_path: Path):
    from gameaihack.publish.kit import inspect_kit, seal_kit

    art = tmp_path / "output" / "美术" / "ui"
    art.mkdir(parents=True)
    (art / "btn.png").write_bytes(b"x")
    design = tmp_path / "output" / "策划"
    design.mkdir(parents=True)
    (design / "02-核心玩法.md").write_text("# 玩法\n", encoding="utf-8")
    (design / "图鉴").mkdir()
    (design / "图鉴" / "README.md").write_text("# 图鉴\n", encoding="utf-8")
    ir = {"package": {"name": "com.example.puzzle"}, "fingerprint": {"engine": "unity"}, "levels": []}
    snap = seal_kit(tmp_path, ir)
    assert (tmp_path / "output" / "复刻说明.md").exists()
    guide = (tmp_path / "output" / "复刻说明.md").read_text(encoding="utf-8")
    assert "对照" in guide
    assert "新游戏" in guide or "制作" in guide
    assert snap["art"]["png"] == 1
    assert snap["remake"]["same_look"] is True
    assert inspect_kit(tmp_path, ir)["design"]["gallery"] is True


def test_output_dir_harvests_dsh(tmp_path: Path):
    from gameaihack.core.layout import output_dir
    from gameaihack.publish.projects import harvest_dsh

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
    monkeypatch.setattr("gameaihack.agent.dsh.dsh_argv", lambda: None)
    try:
        require_dsh()
    except DshError as e:
        assert "必须" in str(e)
    else:
        raise AssertionError("expected DshError")


def test_event_grouper_joins_think_write_tools():
    from gameaihack.agent.drivers.grok import EventGrouper

    lines: list[str] = []
    g = EventGrouper(lines.append)
    for w in ("The", "machine", "claims", "about", "merge."):
        g.feed(json.dumps({"type": "thought", "data": w}))
    g.feed(
        json.dumps(
            {
                "type": "tool_call",
                "toolName": "read_file",
                "rawInput": {"path": "/tmp/job/raw/AGENTS.md"},
            }
        )
    )
    g.feed(json.dumps({"type": "tool_call_update", "status": "completed", "toolCallId": "uuid-1"}))
    g.feed(json.dumps({"type": "text", "data": "目录"}))
    g.feed(json.dumps({"type": "text", "data": "字符串已经指向章节。"}))
    g.close()
    blob = "\n".join(lines)
    assert "think" in blob
    assert "The machine claims about merge." in blob
    assert "tools" in blob
    assert "read_file" in blob
    assert "uuid-1" not in blob
    assert "write" in blob
    assert "目录字符串已经指向章节。" in blob


def test_grok_format_event_streaming_json():
    from gameaihack.agent.drivers.grok import _format_event

    assert _format_event('{"type":"text","data":"写封面"}') == "写 写封面"
    assert _format_event('{"type":"thought","data":"先读 raw"}') == "想 先读 raw"
    assert "read_file" in (
        _format_event(
            '{"type":"tool_call","toolName":"read_file","title":"Read",'
            '"rawInput":{"path":"raw/ir/game.ir.json"}}'
        )
        or ""
    )
    assert "raw/ir/game.ir.json" in (
        _format_event(
            '{"type":"tool_call","toolName":"read_file","rawInput":{"path":"raw/ir/game.ir.json"}}'
        )
        or ""
    )
    assert "完成" in (_format_event('{"type":"tool_call_update","status":"completed","title":"Read"}') or "")
    assert "失败" in (_format_event('{"type":"tool_call_update","status":"failed","toolCallId":"c1"}') or "")
    assert _format_event('{"type":"end","stopReason":"end_turn"}') is None


def test_grok_driver_fake_popen(tmp_path: Path):
    import io

    from gameaihack.agent.drivers.grok import GrokDriver, isolate_job_workspace
    from gameaihack.agent.drivers.types import AgentRequest

    output = (
        '{"type":"thought","data":"先读 raw"}\n'
        '{"type":"tool_call","toolName":"read_file","rawInput":{"path":"raw/AGENTS.md"}}\n'
        '{"type":"text","data":"写好了"}\n'
        '{"type":"end","stopReason":"end_turn"}\n'
    )

    class FakePopen:
        def __init__(self, argv, **kwargs):
            self.argv = list(argv)
            self.stdout = io.StringIO(output)
            self.stdin = io.StringIO()
            self.pid = 1
            FakePopen.seen = self.argv

        def poll(self):
            if self.stdout.tell() >= len(output):
                return 0
            return None

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            pass

        def kill(self):
            pass

    notes: list[str] = []
    drv = GrokDriver(binary="grok", popen=FakePopen)
    result = drv.run(
        AgentRequest(job_dir=tmp_path, prompt="写策划", model="grok-4.6", on_line=notes.append)
    )
    assert result["ok"], result
    assert "写好了" in result["text"]
    assert any("read_file" in n for n in notes)
    assert "--prompt-file" in FakePopen.seen
    assert "--output-format" in FakePopen.seen
    isolate_job_workspace(tmp_path)
    assert (tmp_path / ".git").exists()


def test_codex_driver_fake_popen(tmp_path: Path):
    import io

    from gameaihack.agent.drivers.codex import CodexDriver
    from gameaihack.agent.drivers.types import AgentRequest

    output = '{"type":"item","item":{"text":"ok"}}\n'

    class FakePopen:
        def __init__(self, argv, **kwargs):
            self.argv = list(argv)
            self.stdout = io.StringIO(output)
            self.stdin = io.StringIO()
            self.pid = 1
            FakePopen.seen = self.argv

        def poll(self):
            if self.stdout.tell() >= len(output):
                return 0
            return None

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            pass

        def kill(self):
            pass

    drv = CodexDriver(binary="codex", popen=FakePopen)
    result = drv.run(AgentRequest(job_dir=tmp_path, prompt="写策划", model="gpt-5"))
    assert result["ok"], result
    assert "exec" in FakePopen.seen
    assert "-C" in FakePopen.seen


def test_default_ports_are_wired():
    from gameaihack.pipeline.adapters import (
        DefaultArtRipper,
        DefaultExtractor,
        LlmDesignAgent,
        default_ports,
    )

    ports = default_ports()
    assert isinstance(ports["extractor"], DefaultExtractor)
    assert isinstance(ports["art"], DefaultArtRipper)
    assert isinstance(ports["agent"], LlmDesignAgent)


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
