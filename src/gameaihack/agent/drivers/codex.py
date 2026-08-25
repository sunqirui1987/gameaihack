"""通过 `codex exec` 当 agent：cwd 是 job，基于 raw/ 读、往 output/策划 写。"""

from __future__ import annotations

import json
import shutil

from .grok import isolate_job_workspace
from .process import iter_process_lines
from .types import AgentError, AgentRequest


def which_codex(binary: str = "codex") -> str | None:
    return shutil.which(binary or "codex")


def codex_argv(*, binary: str, model: str, cwd: str, effort: str = "xhigh") -> list[str]:
    argv = [binary, "exec", "--json", "--full-auto", "-C", cwd]
    if model:
        argv.extend(["-m", model])
    argv.extend(["-c", f'model_reasoning_effort="{effort or "xhigh"}"'])
    argv.append("-")
    return argv


class CodexDriver:
    via = "codex"
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
            )
        return path

    def run(self, req: AgentRequest, *, cfg=None) -> dict:
        binary = self.binary if self.popen is not None else self.require(cfg)
        job_dir = req.job_dir.resolve()
        cwd = job_dir
        isolate_job_workspace(cwd)
        argv = codex_argv(
            binary=binary,
            model=req.model,
            cwd=str(cwd),
            effort=req.effort or "xhigh",
        )
        text_parts: list[str] = []

        def emit(line: str) -> None:
            msg = _format_event(line)
            if not msg:
                return
            from gameaihack.core.progress import stream

            stream(msg)
            if req.on_line:
                req.on_line(msg)
            text_parts.append(msg)

        kwargs = {}
        if self.popen is not None:
            kwargs["popen"] = self.popen
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
