"""通过 grok CLI 当 agent：cwd 是 job，基于 raw/ 读、往 output/策划 写。"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .process import iter_process_lines, write_prompt_file
from .types import AgentError, AgentRequest


_JOB_GITIGNORE = """\
raw/unpacked/
raw/extract/
output/美术/
*.png
*.so
*.apk
*.xapk
*.obb
"""


def isolate_job_workspace(job_dir: Path) -> None:
    """Grok 会从 --cwd 往上走到最近的 .git。job 在仓库 jobs/ 里时，不隔离就会把整个仓库当项目。"""
    job_dir = Path(job_dir)
    ignore = job_dir / ".gitignore"
    if not ignore.exists():
        try:
            ignore.write_text(_JOB_GITIGNORE, encoding="utf-8")
        except OSError:
            pass
    marker = job_dir / ".git"
    if marker.exists():
        return
    try:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=str(job_dir),
            check=False,
            capture_output=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def which_grok(binary: str = "grok") -> str | None:
    found = shutil.which(binary)
    if found:
        return found
    home = Path.home() / ".grok" / "bin" / "grok"
    if home.is_file():
        return str(home)
    return None


def grok_argv(
    *,
    binary: str,
    model: str,
    effort: str,
    prompt_file: str,
    cwd: str,
    max_turns: int = 0,
) -> list[str]:
    argv = [
        binary,
        "--no-alt-screen",
        "--no-auto-update",
        "--no-subagents",
        "--no-plan",
        "--disable-web-search",
        "--always-approve",
        "--permission-mode",
        "bypassPermissions",
        "--cwd",
        cwd,
        "--output-format",
        "streaming-json",
        "--verbatim",
        "--prompt-file",
        prompt_file,
    ]
    if max_turns and int(max_turns) > 0:
        argv.extend(["--max-turns", str(int(max_turns))])
    if model:
        argv.extend(["-m", model])
    argv.extend(["--effort", effort or "xhigh"])
    return argv


class GrokDriver:
    via = "grok"
    kind = "cli"
    name = "Grok CLI"
    endpoint = "grok"

    def __init__(self, binary: str = "grok", *, popen=None):
        self.binary = binary or "grok"
        self.popen = popen

    def require(self, cfg=None) -> str:
        path = which_grok(self.binary)
        if not path:
            raise AgentError(
                "找不到 grok CLI。安装 Grok Build 后保证 `grok` 在 PATH，"
                "或设 GAMEAIHACK_GROK=/绝对路径/grok。"
                "不装 CLI 请用默认 --via sdk（自建 agent）。"
            )
        return path

    def run(self, req: AgentRequest, *, cfg=None) -> dict:
        from gameaihack.agent.harness import cli_home, inject_cli_env, prepare_grok_home
        from gameaihack.core.progress import log, stream

        binary = self.binary if self.popen is not None else self.require(cfg)
        job_dir = req.job_dir.resolve()
        cwd = job_dir
        isolate_job_workspace(cwd)
        model = req.model or (cfg.model if cfg else "")
        env = None
        if cfg and getattr(cfg, "api_key", None):
            home = prepare_grok_home(cli_home(job_dir, "grok"), cfg)
            env = inject_cli_env(cfg, grok_home=home)
            stream(f"grok  CLI  {model or cfg.model}  {cfg.openai_base}")
        else:
            stream("grok  CLI  （本机登录，未注入 LLM_*）")
        folder = tempfile.mkdtemp(prefix="gameaihack-grok-")
        try:
            path = write_prompt_file(req.prompt, directory=folder)
            argv = grok_argv(
                binary=binary,
                model=model,
                effort=req.effort or "xhigh",
                prompt_file=str(path),
                cwd=str(cwd),
            )
            text_parts: list[str] = []

            def publish(msg: str) -> None:
                stream(msg)
                if req.on_line:
                    req.on_line(msg)
                text_parts.append(msg)

            grouper = EventGrouper(publish)

            def emit(line: str) -> None:
                grouper.feed(line)

            kwargs: dict = {}
            if self.popen is not None:
                kwargs["popen"] = self.popen
            if env is not None:
                kwargs["env"] = env
            for line in iter_process_lines(
                argv,
                timeout=req.timeout,
                cwd=cwd,
                on_line=emit,
                **kwargs,
            ):
                _ = line
            grouper.close()
            text = "\n".join(text_parts)
            return {"ok": True, "via": "grok", "text": text, "error": ""}
        except Exception as e:
            log(f"[grok] 失败 {e}")
            return {"ok": False, "via": "grok", "text": "", "error": str(e)}
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class EventGrouper:
    """把 streaming-json 收成 grok CLI 那样的组：想 / 写 / 工具。"""

    def __init__(self, out) -> None:
        self.out = out
        self.kind: str | None = None
        self.parts: list[str] = []
        self.tool_n = 0

    def feed(self, line: str) -> None:
        raw = (line or "").strip()
        if not raw:
            return
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            if len(raw) >= 8:
                self.close()
                self.out(raw[:400])
            return
        if not isinstance(ev, dict):
            return
        typ = str(ev.get("type") or "")
        if typ in {"thought", "text"}:
            self._chunk(typ, _event_text(ev))
        elif typ == "tool_call":
            self._tool(ev)
        elif typ == "tool_call_update":
            if str(ev.get("status") or "") == "failed":
                name = ev.get("toolName") or ev.get("title") or "tool"
                self.out(f"  失败 {name}")
        elif typ in {"error", "max_turns_reached"}:
            self.close()
            self.out(str(ev.get("message") or typ))
        elif typ == "end":
            self.close()

    def flush_text(self) -> None:
        self._emit_parts()

    def close(self) -> None:
        self._emit_parts()
        if self.kind == "tool" and self.tool_n:
            self.out(f"  done {self.tool_n}")
        self.kind = None
        self.tool_n = 0

    def _chunk(self, kind: str, piece: str) -> None:
        if not piece:
            return
        if self.kind != kind:
            self.close()
            self.kind = kind
            self.out("think" if kind == "thought" else "write")
        self.parts.append(piece)
        blob = _join_tokens(self.parts)
        if "\n" in piece or _stop_here(blob):
            self._emit_parts()

    def _emit_parts(self) -> None:
        if not self.parts:
            return
        text = _join_tokens(self.parts).strip()
        self.parts = []
        if not text:
            return
        for row in _wrap(text, 96):
            self.out(row)

    def _tool(self, ev: dict) -> None:
        if self.kind != "tool":
            self.close()
            self.kind = "tool"
            self.out("tools")
            self.tool_n = 0
        name = str(ev.get("toolName") or ev.get("title") or ev.get("kind") or "tool")
        path = _tool_path(ev)
        line = f"  {name}"
        if path:
            line += f"  {path}"
        self.out(line)
        self.tool_n += 1


def _event_text(ev: dict) -> str:
    body = ev.get("data")
    if isinstance(body, dict):
        body = body.get("text") or ""
    return str(body or "")


def _join_tokens(parts: list[str]) -> str:
    out = ""
    for p in parts:
        if not p:
            continue
        if (
            out
            and out[-1].isascii()
            and out[-1].isalnum()
            and p[0].isascii()
            and p[0].isalnum()
        ):
            out += " "
        out += p
    return out


def _stop_here(blob: str) -> bool:
    s = blob.rstrip()
    if len(s) >= 160:
        return True
    return s.endswith(("。", "！", "？", ".", "!", "?", "：", ":")) and len(s) >= 24


def _wrap(text: str, width: int) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= width:
        return [text]
    rows: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if len(buf) >= width and ch in " ，,。；; ":
            rows.append(buf.strip())
            buf = ""
    if buf.strip():
        rows.append(buf.strip())
    return rows or [text]


def _tool_path(ev: dict) -> str:
    raw_in = ev.get("rawInput") if isinstance(ev.get("rawInput"), dict) else {}
    path = str(
        raw_in.get("path")
        or raw_in.get("target_file")
        or raw_in.get("file_path")
        or raw_in.get("command")
        or raw_in.get("pattern")
        or ""
    )
    p = path.replace("\\", "/")
    for mark in ("/output/", "/raw/"):
        i = p.find(mark)
        if i >= 0:
            return p[i + 1 :]
    if len(p) > 64:
        return "…" + p[-60:]
    return p


def _format_event(line: str) -> str | None:
    """对照 grok --output-format streaming-json 的 ACP 事件。"""
    raw = (line or "").strip()
    if not raw:
        return None
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        if len(raw) < 8:
            return None
        return raw[:400]
    if not isinstance(ev, dict):
        return raw[:400]
    typ = str(ev.get("type") or "")
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    if typ in {"text", "thought"}:
        body = ev.get("data")
        if isinstance(body, dict):
            body = body.get("text") or ""
        body = str(body or "").replace("\n", " ").strip()
        if not body:
            return None
        tag = "想" if typ == "thought" else "写"
        return f"{tag} {body[:240]}"
    if typ == "tool_call":
        name = ev.get("toolName") or ev.get("title") or ev.get("kind") or "tool"
        raw_in = ev.get("rawInput") if isinstance(ev.get("rawInput"), dict) else {}
        path = str(
            raw_in.get("path")
            or raw_in.get("target_file")
            or raw_in.get("file_path")
            or raw_in.get("command")
            or raw_in.get("pattern")
            or ""
        )
        extra = f" {path}" if path else ""
        return f"工具 {name}{extra}"
    if typ == "tool_call_update":
        status = str(ev.get("status") or "")
        if status == "failed":
            return f"工具失败 {ev.get('toolCallId') or ''}".strip()
        if status == "completed":
            return f"工具完成 {ev.get('title') or ev.get('toolName') or ev.get('toolCallId') or ''}".strip()
        return None
    if typ == "plan":
        return "更新计划"
    if typ in {"error", "max_turns_reached"}:
        return str(ev.get("message") or typ)
    if typ.endswith("/error"):
        return str(data.get("message") or ev.get("message") or raw[:200])
    return None
