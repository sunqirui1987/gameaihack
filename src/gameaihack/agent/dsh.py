"""DeepSeek Harness：读 jobs/<包>/raw，写 output/策划。

真正入口是 npm 包 @deepseek-ai/dsh（headless profile），不是 PyPI 上的占位 SDK。
本机 Node 23 不满足引擎约束（要 ^22.19 或 >=24），所以优先用 nvm 里的 22/24。
密钥走和 llm_bench 一样的 LLM_API_KEY / LLM_BASE_URL，映射成 DEEPSEEK_*。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from gameaihack.agent.drivers.types import AgentError
from gameaihack.agent.llm import LlmConfig

INSTALL = """DSH 是必须的（https://github.com/deepseek-ai/deepseek-harness）。

当前默认 node 23 不能跑 dsh，要用 22.19+ 或 24+。

  export PATH="$HOME/.nvm/versions/node/v22.18.0/bin:$PATH"
  mkdir -p .dsh && npm install --prefix .dsh @deepseek-ai/dsh

或全局：npm install -g @deepseek-ai/dsh
或指定：export GAMEAIHACK_DSH=/绝对路径/dsh

模型密钥与 llm_bench 相同（会映射成 DEEPSEEK_*）：
  export LLM_API_KEY=...
  export LLM_BASE_URL=http://127.0.0.1:8080
  export LLM_MODELS=grok-4.6
"""


class DshError(AgentError):
    pass


def require_dsh() -> list[str]:
    argv = dsh_argv()
    if not argv:
        raise DshError(INSTALL)
    return argv

NVM_NODE = Path.home() / ".nvm" / "versions" / "node"
_VER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def _parse_ver(name: str) -> tuple[int, int, int] | None:
    m = _VER.match(name.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _node_ok(ver: tuple[int, int, int]) -> bool:
    major, minor, _ = ver
    if major >= 24:
        return True
    # 官方写 ^22.19；22.18 实测也能跑 launcher
    if major == 22 and minor >= 18:
        return True
    return False


def _compatible_node_bin() -> Path | None:
    env_node = shutil.which("node")
    if env_node:
        try:
            out = subprocess.check_output([env_node, "-v"], text=True, timeout=5).strip()
        except (OSError, subprocess.SubprocessError):
            out = ""
        ver = _parse_ver(out)
        if ver and _node_ok(ver):
            return Path(env_node).parent
    if NVM_NODE.is_dir():
        scored: list[tuple[tuple[int, int, int], Path]] = []
        for child in NVM_NODE.iterdir():
            ver = _parse_ver(child.name)
            if not ver or not _node_ok(ver):
                continue
            bin_dir = child / "bin"
            if (bin_dir / "node").exists():
                scored.append((ver, bin_dir))
        if scored:
            scored.sort()
            return scored[-1][1]
    return None


def _project_dsh() -> Path | None:
    here = Path(__file__).resolve()
    roots = [here.parents[3], here.parents[1], Path.cwd(), Path.home()]
    for root in roots:
        for cand in (
            root / ".dsh" / "node_modules" / ".bin" / "dsh",
            root / "node_modules" / ".bin" / "dsh",
        ):
            if cand.is_file() or cand.is_symlink():
                return cand
    return None


def dsh_argv() -> list[str] | None:
    """可执行的 dsh 命令前缀。没有则 None。"""
    explicit = (os.environ.get("GAMEAIHACK_DSH") or "").strip()
    if explicit:
        return explicit.split()
    local = _project_dsh()
    node_bin = _compatible_node_bin()
    path_extra = str(node_bin) if node_bin else ""
    if local:
        return [str(local)]
    which = shutil.which("dsh", path=f"{path_extra}:{os.environ.get('PATH', '')}" if path_extra else None)
    if which:
        return [which]
    npx = shutil.which("npx", path=f"{path_extra}:{os.environ.get('PATH', '')}" if path_extra else None)
    if npx:
        return [npx, "--yes", "@deepseek-ai/dsh"]
    return None


def dsh_available() -> str | None:
    argv = dsh_argv()
    if not argv:
        return None
    if argv[0].endswith("/dsh") or argv[0].endswith("dsh"):
        return "cli"
    if "npx" in argv[0] or argv[0].endswith("npx"):
        return "npx"
    return "cli"


PERSONA = (
    "先读 output/策划/_事实源.md，那是 raw 清单和美术清单合成的事实源。"
    "只能改 output/策划/（不要动 _事实源.md）和 清单.md、清单/。不要改 raw/、output/美术/。"
    "策划只准写事实源里有的系统、表、关卡、美术目录。"
    "图鉴文件名必须等于美术清单文件夹；嵌图必须是清单里的 path。"
    "写可开工的制作说明书：整局过程、02 能做第一局、制作顺序.md。"
    "看美术用 美术/清单/，不要枚举上万 png。没证据标未知。"
    "不要发明目录、不要编造坐标、不要写盗版客户端。"
)


def prepare_grok_home(dsh_home: Path, cfg: LlmConfig, sessions: Path | None = None) -> Path:
    """写出 DSH settings + patch，把默认模型接到 Grok（OpenAI 兼容网关）。"""
    import yaml

    dsh_home.mkdir(parents=True, exist_ok=True)
    session_root = (sessions or (dsh_home / "sessions")).resolve()
    session_root.mkdir(parents=True, exist_ok=True)
    for stale in session_root.rglob("session.jsonl.zstd"):
        try:
            stale.unlink()
        except OSError:
            pass
    settings = {
        "llm-pi-ai": {
            "providers": {
                "grok": {
                    "displayName": "Grok",
                    "apiKeyEnv": "LLM_API_KEY",
                    "api": "openai-completions",
                    "baseURL": cfg.openai_base,
                    "compat": {
                        "supportsDeveloperRole": False,
                        "maxTokensField": "max_tokens",
                    },
                    "models": [
                        {
                            "id": cfg.model,
                            "name": cfg.model,
                            "contextWindow": 1_000_000,
                            "maxTokens": 65_536,
                        }
                    ],
                }
            }
        }
    }
    settings_path = dsh_home / "settings.yaml"
    settings_path.write_text(
        yaml.safe_dump(settings, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    patch = [
        {
            "id": "agent-default-model",
            "config": {"provider": "grok", "model": cfg.model},
        },
        {
            "id": "llm-pi-ai",
            "config": settings["llm-pi-ai"],
        },
        {
            "id": "session-persistence-jsonl",
            "config": {
                "root": str(session_root),
                "compression": "none",
                "packChunks": False,
            },
        },
        {
            "id": "system-prompt",
            "config": {"persona": PERSONA},
        },
    ]
    patch_path = dsh_home / "grok.patch.yml"
    patch_path.write_text(
        yaml.safe_dump(patch, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return patch_path


def _export_llm_env(cfg: LlmConfig, cwd: Path, sessions: Path, dsh_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    node_bin = _compatible_node_bin()
    if node_bin:
        env["PATH"] = f"{node_bin}{os.pathsep}{env.get('PATH', '')}"
    env["DEEPSEEK_API_KEY"] = cfg.api_key
    env["DEEPSEEK_BASE_URL"] = cfg.openai_base
    env["OPENAI_API_KEY"] = cfg.api_key
    env["OPENAI_BASE_URL"] = cfg.openai_base
    env["LLM_API_KEY"] = cfg.api_key
    env["LLM_BASE_URL"] = cfg.base_url
    env["DSH_MODEL"] = cfg.model
    env["LLM_MODELS"] = cfg.model
    env["DSH_CWD"] = str(cwd)
    env["DSH_SESSION_ROOT"] = str(sessions)
    env["DSH_HOME"] = str(dsh_home)
    env["DSH_PERMISSION_MODE"] = "danger-full-access"
    env["DSH_TELEMETRY_MODE"] = "DISABLED"
    env["DSH_SYSTEM_PROMPT"] = PERSONA
    return env


def run_dsh(
    job_dir: Path,
    prompt: str,
    cfg: LlmConfig,
    *,
    timeout: int = 1800,
    on_line=None,
) -> dict:
    """cwd=job_dir（可见 raw/ 与 output/），headless 跑完退出。"""
    import time
    from gameaihack.core.layout import raw_dir
    from gameaihack.core.progress import log

    argv = require_dsh()
    cwd = job_dir.resolve()
    raw = raw_dir(job_dir)
    if not raw.is_dir():
        raw = job_dir / "raw"
        raw.mkdir(parents=True, exist_ok=True)
    dsh_home = (raw / "_dsh_home").resolve()
    sessions = dsh_home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    patch = prepare_grok_home(dsh_home, cfg, sessions=sessions)
    env = _export_llm_env(cfg, cwd, sessions, dsh_home)
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [*argv, "--profile", "headless", "--patch", str(patch), prompt]
    via = "npx" if cmd[0].endswith("npx") or "npx" in Path(cmd[0]).name else "cli"
    log_path = raw / "dsh.log"
    t0 = time.time()

    def emit(msg: str) -> None:
        line = msg.rstrip("\n")
        if not line:
            return
        log(line)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if on_line:
            try:
                on_line(line)
            except Exception:
                pass

    emit(f"[dsh] 开始  model={cfg.model}  provider=grok  url={cfg.openai_base}")
    emit(f"[dsh] 工作区 {cwd}  （读 raw/，写 output/）")
    emit(f"[dsh] 日志    {log_path}")
    emit(f"[dsh] 命令    {' '.join(cmd[:6])} …")
    stdout_chunks: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as e:
        return {"ok": False, "via": via, "text": "", "error": str(e)}

    sess_state = {"path": None, "pos": 0, "buf": ""}
    last_beat = t0
    try:
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            now = time.time()
            if line:
                stdout_chunks.append(line)
                emit("[dsh] " + line.rstrip("\n"))
                last_beat = now
            _drain_session_log(dsh_home, sess_state, emit)
            if proc.poll() is not None:
                if proc.stdout:
                    rest = proc.stdout.read() or ""
                    if rest:
                        stdout_chunks.append(rest)
                        for ln in rest.splitlines():
                            emit("[dsh] " + ln)
                _drain_session_log(dsh_home, sess_state, emit)
                break
            if now - t0 > timeout:
                proc.kill()
                emit(f"[dsh] 超时 {timeout}s，已杀掉")
                return {"ok": False, "via": via, "text": "".join(stdout_chunks).strip(), "error": f"timeout {timeout}s"}
            if not line:
                if now - last_beat >= 15:
                    emit(f"[dsh] 仍在跑 … {int(now - t0)}s  （完整日志 {log_path}）")
                    last_beat = now
                time.sleep(0.15)
    except Exception as e:
        proc.kill()
        return {"ok": False, "via": via, "text": "".join(stdout_chunks).strip(), "error": str(e)}
    code = proc.returncode or 0
    text = "".join(stdout_chunks).strip()
    emit(f"[dsh] 结束  exit={code}  耗时 {int(time.time() - t0)}s")
    if code != 0:
        return {"ok": False, "via": via, "text": text[-8000:], "error": text[-800:] or f"exit {code}"}
    return {"ok": True, "via": via, "text": text, "error": ""}


def _drain_session_log(dsh_home: Path, state: dict, emit) -> None:
    import json

    sess = dsh_home / "sessions"
    if not sess.is_dir():
        return
    files = list(sess.rglob("session.jsonl")) + list(sess.rglob("session.jsonl.zstd"))
    if not files:
        return
    path = max(files, key=lambda p: p.stat().st_mtime)
    if state["path"] != path:
        state["path"] = path
        state["pos"] = 0
        state["buf"] = ""
        emit(f"[dsh] 会话 {path.relative_to(dsh_home)}")
    if path.suffix == ".zstd":
        return
    try:
        data = path.read_bytes()
    except OSError:
        return
    if len(data) <= state["pos"]:
        return
    chunk = data[state["pos"] :]
    state["pos"] = len(data)
    text = state["buf"] + chunk.decode("utf-8", "replace")
    parts = text.split("\n")
    state["buf"] = parts[-1]
    for raw in parts[:-1]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            emit("[dsh] " + raw[:300])
            continue
        msg = _format_session_event(ev)
        if msg:
            emit("[dsh] " + msg)


def _format_session_event(ev: dict) -> str | None:
    t = str(ev.get("type") or "")
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    if t == "turn/start":
        return f"回合 {data.get('turn')} 开始"
    if t == "step/start":
        return f"step {data.get('step')}"
    if t == "step/end":
        return f"step {data.get('step')} 结束"
    if t == "turn/end":
        return f"回合 {data.get('turn')} 结束"
    if t in {"sandbox/mode", "permission/preset", "approval/policy"}:
        return f"{t.split('/')[0]}={next(iter(data.values()), '')}"
    if t == "assistant/chunk":
        chunk = data.get("chunk") if isinstance(data.get("chunk"), dict) else {}
        if chunk.get("type") == "text" and chunk.get("text"):
            return chunk["text"].replace("\n", "\n[dsh] ")
        reason = (chunk.get("reason") or {}) if chunk.get("type") == "finish" else {}
        if isinstance(reason, dict) and reason.get("kind") == "error":
            fail = reason.get("failure") or {}
            return f"模型错误：{fail.get('message') or reason}"
        return None
    if t == "assistant/message":
        content = data.get("content") or []
        texts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                texts.append(c.get("text") or "")
        if texts:
            body = "\n".join(texts)
            return "回复：\n[dsh] " + body.replace("\n", "\n[dsh] ")[:2000]
        return None
    if "tool" in t:
        name = data.get("name") or data.get("tool") or data.get("id") or t
        detail = (
            data.get("command")
            or data.get("path")
            or data.get("file")
            or data.get("target")
            or data.get("input")
            or ""
        )
        if isinstance(detail, dict):
            bits = []
            for k in ("path", "file", "command", "target_file", "file_path", "content"):
                if detail.get(k):
                    v = str(detail[k])
                    bits.append(f"{k}={v[:180]}")
            detail = " ".join(bits) or str(detail)[:240]
        verb = "开始" if t.endswith("/start") or t.endswith("/call") else ("结束" if t.endswith("/end") or t.endswith("/result") else "")
        return f"{verb}工具 {name} {str(detail)[:300]}".strip()
    if t in {"request/header", "request/context"}:
        model = data.get("model") or (data.get("header") or {}).get("model")
        if model:
            return f"请求模型 {model}"
        return None
    if t.endswith("/error") or t == "error":
        return f"错误 {data.get('message') or data}"
    return None
