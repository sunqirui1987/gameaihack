"""自建 agent：官方 DeepSeek Harness Python SDK（JSON-RPC 子进程）。

宿主把 LLM_* 映射成 DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY，cwd 是 job。
三次策划任务复用同一个 runtime 和同一条 session。
文档：https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from gameaihack.agent.dsh import PERSONA
from gameaihack.agent.drivers.types import AgentError, AgentRequest
from gameaihack.agent.llm import LlmConfig, resolve_llm
from gameaihack.core.progress import stream

INSTALL = (
    "自建 agent 用 DeepSeek Harness Python SDK。\n"
    "  pip install 'deepseek-harness-sdk'\n"
    "会同时安装同版本 deepseek-harness-runtime-bin（macOS 14+ arm64 或 Linux）。\n"
    "本机 grok/codex CLI 请用 --via grok 或 --via codex。"
)


def bundled_cordis() -> Path:
    path = Path(__file__).resolve().parents[1] / "data" / "dsh.cordis.yml"
    if not path.is_file():
        raise AgentError(f"找不到 DSH cordis：{path}")
    return path


def resolve_runtime_bin() -> str | None:
    """捆绑 dsh-jsonrpc-agent。Rosetta x86_64 Python 仍可跑 arm64 二进制。"""
    explicit = (os.environ.get("GAMEAIHACK_DSH_RUNTIME") or "").strip()
    if explicit:
        return explicit
    try:
        from deepseek_harness_runtime import bundled_runtime_path

        return str(bundled_runtime_path())
    except Exception:
        pass
    try:
        import deepseek_harness_runtime

        root = Path(deepseek_harness_runtime.__file__).resolve().parent / "runtime"
    except Exception:
        return None
    names = (
        "dsh-jsonrpc-agent-pkg-macos-arm64",
        "dsh-jsonrpc-agent-pkg-linux-arm64",
        "dsh-jsonrpc-agent-pkg-linux-x64",
        "dsh-jsonrpc-agent-pkg-macos-x64",
    )
    for name in names:
        cand = root / name
        if cand.is_file():
            return str(cand)
    return None


def _import_harness():
    try:
        from deepseek_harness import DeepSeekHarness
    except ImportError as e:
        raise AgentError(INSTALL) from e
    return DeepSeekHarness


def _payload(note) -> tuple[str, dict]:
    if isinstance(note, dict):
        method = str(note.get("method") or "")
        payload = note.get("payload") if isinstance(note.get("payload"), dict) else {}
        return method, payload
    method = str(getattr(note, "method", "") or "")
    raw = getattr(note, "payload", None)
    payload = raw if isinstance(raw, dict) else {}
    return method, payload


def _emit_note(note, publish) -> None:
    method, payload = _payload(note)
    if method == "session.event":
        ev = payload.get("event")
        if isinstance(ev, dict):
            from gameaihack.agent.dsh import _format_session_event

            msg = _format_session_event(ev)
            if msg:
                publish(msg)
        return
    if method == "session.status":
        status = str(payload.get("status") or "")
        if status and status not in {"idle", "running"}:
            publish(status)


def _design_written(job: Path) -> bool:
    dest = job / "output" / "策划"
    if not dest.is_dir():
        return False
    for path in dest.rglob("*.md"):
        rel = path.relative_to(dest).as_posix()
        if path.name == "_事实源.md" or rel.startswith("ai/"):
            continue
        return True
    return False


def harness_kwargs(req: AgentRequest, cfg: LlmConfig) -> dict:
    model = (req.model or cfg.model or "").split(",", 1)[0].strip()
    job = req.job_dir.resolve()
    sessions = job / "raw" / "_dsh_home" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "provider": "deepseek-official",
        "model": model,
        "cwd": str(job),
        "session_root": str(sessions.resolve()),
        "cordis": str(bundled_cordis()),
        "base_url": cfg.openai_base,
        "api_key": cfg.api_key,
        "env": {
            "DSH_MODEL": model,
            "DSH_SYSTEM_PROMPT": PERSONA,
            "DSH_CONTEXT_WINDOW": "1000000",
            "DSH_PERMISSION_MODE": "danger-full-access",
            "DSH_TELEMETRY_MODE": "DISABLED",
            "LLM_API_KEY": cfg.api_key,
            "LLM_BASE_URL": cfg.base_url,
            "LLM_MODELS": model,
        },
        "request_timeout_seconds": float(req.timeout or 3600),
    }
    runtime = resolve_runtime_bin()
    if runtime:
        kwargs["runtime_bin"] = runtime
    return kwargs


def _finish(result, job: Path, via: str) -> dict:
    text = str(getattr(result, "final_response", "") or "")
    reason = getattr(result, "finish_reason", None)
    if reason == "error":
        return {"ok": False, "via": via, "text": text, "error": text[-400:] or "dsh finish_reason=error"}
    if not _design_written(job) and not text:
        return {"ok": False, "via": via, "text": text, "error": "DSH 结束但没有写出策划文件"}
    return {"ok": True, "via": via, "text": text, "error": "", "finish_reason": reason or ""}


def _prompt_on(harness, req: AgentRequest, *, via: str, session_id: str) -> dict:
    def publish(msg: str) -> None:
        text = (msg or "").rstrip("\n")
        if not text:
            return
        stream(text)
        if req.on_line:
            req.on_line(text)

    result = harness.run(
        req.prompt,
        session_id=session_id,
        on_notification=lambda n: _emit_note(n, publish),
    )
    return _finish(result, req.job_dir.resolve(), via)


def run_sdk(
    req: AgentRequest,
    *,
    cfg: LlmConfig | None = None,
    via: str = "sdk",
    harness_cls=None,
) -> dict:
    cfg = cfg or resolve_llm()
    if cfg is None or not cfg.api_key:
        raise AgentError("请设 LLM_API_KEY、LLM_BASE_URL、LLM_MODELS。自建 agent 会注入 DeepSeek Harness。")
    model = (req.model or cfg.model or "").split(",", 1)[0].strip()
    Harness = harness_cls or _import_harness()
    stream(f"{via}  dsh  {model}  {cfg.openai_base}")
    kwargs = harness_kwargs(req, cfg)
    session_id = f"{req.job_dir.resolve().name}-{int(time.time())}"
    try:
        with Harness(**kwargs) as harness:
            return _prompt_on(harness, req, via=via, session_id=session_id)
    except AgentError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "via": via, "text": "", "error": f"{type(e).__name__}: {e}"}


class SdkDriver:
    """DeepSeek Harness Python SDK。一次 analyze 复用同一个 runtime / session。"""

    kind = "sdk"
    name = "DeepSeek Harness SDK"
    endpoint = "dsh-jsonrpc-agent"

    def __init__(self, via: str = "sdk"):
        self.via = via or "sdk"
        self._harness = None
        self._session_id = ""
        self._label = False

    def close(self) -> None:
        h = self._harness
        self._harness = None
        if h is None:
            return
        closer = getattr(h, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass

    def require(self, cfg=None):
        cfg = cfg or resolve_llm()
        if cfg is None or not getattr(cfg, "api_key", None):
            raise AgentError(
                "自建 agent（--via sdk）请设 LLM_API_KEY、LLM_BASE_URL、LLM_MODELS。"
                "本机 grok/codex CLI 请用 --via grok 或 --via codex。"
            )
        _import_harness()
        bundled_cordis()
        if resolve_runtime_bin() is None:
            raise AgentError(INSTALL + "\n已能 import SDK，但找不到 dsh-jsonrpc-agent runtime。")
        return cfg

    def run(self, req: AgentRequest, *, cfg=None) -> dict:
        try:
            cfg = cfg or resolve_llm()
            if cfg is None or not cfg.api_key:
                raise AgentError("请设 LLM_API_KEY、LLM_BASE_URL、LLM_MODELS。")
            if not self._label:
                stream(f"{self.via}  dsh  {cfg.model}  {cfg.openai_base}")
                self._label = True
            if self._harness is None:
                Harness = _import_harness()
                self._harness = Harness(**harness_kwargs(req, cfg))
                self._session_id = f"{req.job_dir.resolve().name}-{int(time.time())}"
            return _prompt_on(self._harness, req, via=self.via, session_id=self._session_id)
        except AgentError as e:
            self.close()
            return {"ok": False, "via": self.via, "text": "", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            self.close()
            return {"ok": False, "via": self.via, "text": "", "error": f"{type(e).__name__}: {e}"}
