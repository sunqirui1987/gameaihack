"""通过 `codex exec` 当 agent：cwd 是 job，基于 raw/ 读、往 output/策划 写。

有 LLM_* 时按 Cindy harness 注入独立 CODEX_HOME + model_provider（默认 wire_api=chat，
不把网关模型塞进官方 /responses）。没有 LLM_* 时用本机 Codex 登录。
"""

from __future__ import annotations

import json
import shutil

from .grok import isolate_job_workspace
from .process import iter_process_lines
from .types import AgentError, AgentRequest
from gameaihack.agent.llm import LlmConfig


def which_codex(binary: str = "codex") -> str | None:
    return shutil.which(binary or "codex")


def codex_argv(
    *,
    binary: str,
    model: str,
    cwd: str,
    effort: str = "xhigh",
    cfg: LlmConfig | None = None,
) -> list[str]:
    argv = [binary, "exec", "--json", "--sandbox", "workspace-write", "-C", cwd]
    if cfg and getattr(cfg, "api_key", None):
        from gameaihack.agent.harness import codex_provider_argv

        argv.extend(codex_provider_argv(cfg))
    if model:
        argv.extend(["-m", model])
    argv.extend(["-c", f'model_reasoning_effort="{effort or "xhigh"}"'])
    argv.append("-")
    return argv


class CodexDriver:
    via = "codex"
    kind = "cli"
    name = "Codex CLI"
    endpoint = "codex exec"

    def __init__(self, binary: str = "codex", *, popen=None):
        self.binary = binary or "codex"
        self.popen = popen

    def require(self, cfg=None) -> str:
        path = which_codex(self.binary)
        if not path:
            raise AgentError(
                "找不到 Codex CLI。安装 `codex` 并保证在 PATH，"
                "或设 GAMEAIHACK_CODEX=/绝对路径/codex。"
                "不装 CLI 请用默认 --via sdk（自建 agent）。"
            )
        return path

    def run(self, req: AgentRequest, *, cfg=None) -> dict:
        from gameaihack.agent.harness import cli_home, inject_cli_env, prepare_codex_home
        from gameaihack.core.progress import stream

        binary = self.binary if self.popen is not None else self.require(cfg)
        job_dir = req.job_dir.resolve()
        cwd = job_dir
        isolate_job_workspace(cwd)
        model = req.model or (cfg.model if cfg else "")
        env = None
        if cfg and getattr(cfg, "api_key", None):
            home = prepare_codex_home(cli_home(job_dir, "codex"), cfg)
            env = inject_cli_env(cfg, codex_home=home)
            stream(f"codex  CLI  {model or cfg.model}  {cfg.openai_base}")
        else:
            stream("codex  CLI  （本机登录，未注入 LLM_*）")
        argv = codex_argv(
            binary=binary,
            model=model,
            cwd=str(cwd),
            effort=req.effort or "xhigh",
            cfg=cfg if (cfg and getattr(cfg, "api_key", None)) else None,
        )
        text_parts: list[str] = []

        def emit(line: str) -> None:
            msg = _format_event(line)
            if not msg:
                return
            stream(msg)
            if req.on_line:
                req.on_line(msg)
            text_parts.append(msg)

        kwargs: dict = {}
        if self.popen is not None:
            kwargs["popen"] = self.popen
        if env is not None:
            kwargs["env"] = env
        try:
            for line in iter_process_lines(
                argv,
                timeout=req.timeout,
                cwd=cwd,
                stdin_text=req.prompt,
                on_line=emit,
                **kwargs,
            ):
                _ = line
        except Exception as e:
            return {"ok": False, "via": "codex", "text": "", "error": str(e)}
        return {"ok": True, "via": "codex", "text": "\n".join(text_parts), "error": ""}


def _format_event(line: str) -> str | None:
    raw = (line or "").strip()
    if not raw:
        return None
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:400]
    if not isinstance(ev, dict):
        return raw[:400]
    if ev.get("type") in {"error", "turn.failed"}:
        return str(ev.get("message") or ev)[:300]
    item = ev.get("item") or ev.get("msg") or {}
    if isinstance(item, dict):
        text = str(item.get("text") or item.get("content") or "")
        if text:
            return text[:500]
    return None
