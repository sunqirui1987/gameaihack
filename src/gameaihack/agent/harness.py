"""Cindy 式 CLI harness：宿主注入 model / baseUrl / key，隔离官方账号目录。

自建 agent 在 sdk.py。本模块只服务 --via grok|codex 这类本机 CLI：
把 LLM_* 写进子进程环境，并给一份独立 GROK_HOME / CODEX_HOME，
不读用户 ~/.grok、~/.codex 里的官方登录。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from gameaihack.agent.llm import LlmConfig, env

CODEX_PROVIDER = "gameaihack"


def grok_api_backend() -> str:
    raw = env("LLM_API_BACKEND", "GAMEAIHACK_API_BACKEND").strip().lower()
    if raw in {"responses", "response"}:
        return "responses"
    if raw in {"messages", "anthropic"}:
        return "messages"
    return "chat_completions"


def codex_wire_api() -> str:
    raw = env("LLM_API_BACKEND", "GAMEAIHACK_API_BACKEND", "GAMEAIHACK_CODEX_WIRE").strip().lower()
    if raw in {"responses", "response"}:
        return "responses"
    return "chat"


def _toml_key(name: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", name or ""):
        return name
    escaped = (name or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def prepare_grok_home(root: Path, cfg: LlmConfig) -> Path:
    """独立 GROK_HOME：自定义模型指向宿主网关，密钥只走环境变量。"""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "sessions").mkdir(exist_ok=True)
    model = (cfg.model or "default").strip()
    backend = grok_api_backend()
    text = (
        "[cli]\n"
        "auto_update = false\n\n"
        "[features]\n"
        "telemetry = false\n"
        "remote_fetch = false\n\n"
        "[models]\n"
        f"default = {_toml_str(model)}\n"
        'default_reasoning_effort = "xhigh"\n\n'
        f"[model.{_toml_key(model)}]\n"
        f"model = {_toml_str(model)}\n"
        f"base_url = {_toml_str(cfg.openai_base)}\n"
        'name = "gameaihack"\n'
        'env_key = "LLM_API_KEY"\n'
        f"api_backend = {_toml_str(backend)}\n"
        "context_window = 1000000\n"
    )
    (root / "config.toml").write_text(text, encoding="utf-8")
    return root


def prepare_codex_home(root: Path, cfg: LlmConfig) -> Path:
    """独立 CODEX_HOME，避免读到用户 ~/.codex 里的官方 / 第三方账号。"""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    model = (cfg.model or "").strip()
    wire = codex_wire_api()
    lines = [
        f'model_provider = "{CODEX_PROVIDER}"',
        f'model_reasoning_effort = "xhigh"',
        "",
        f"[model_providers.{CODEX_PROVIDER}]",
        'name = "gameaihack"',
        f"base_url = {_toml_str(cfg.openai_base)}",
        f'wire_api = "{wire}"',
        'env_key = "OPENAI_API_KEY"',
        "supports_websockets = false",
        "",
    ]
    if model:
        lines.insert(0, f"model = {_toml_str(model)}")
    (root / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def cli_home(job_dir: Path, name: str) -> Path:
    return Path(job_dir).resolve() / "raw" / "_cli_home" / name


def inject_cli_env(
    cfg: LlmConfig,
    *,
    grok_home: Path | None = None,
    codex_home: Path | None = None,
) -> dict[str, str]:
    """把宿主的 model / baseUrl / key 注入 CLI 进程，对齐 Cindy getAuthEnv。"""
    env_map = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    env_map["LLM_API_KEY"] = cfg.api_key
    env_map["LLM_BASE_URL"] = cfg.base_url
    env_map["LLM_MODELS"] = cfg.model
    env_map["OPENAI_API_KEY"] = cfg.api_key
    env_map["OPENAI_BASE_URL"] = cfg.openai_base
    env_map["OPENAI_MODEL"] = cfg.model
    env_map["XAI_API_KEY"] = cfg.api_key
    env_map["GROK_CODE_XAI_API_KEY"] = cfg.api_key
    env_map["GROK_MODELS_BASE_URL"] = cfg.openai_base
    env_map["DEEPSEEK_API_KEY"] = cfg.api_key
    env_map["DEEPSEEK_BASE_URL"] = cfg.openai_base
    env_map.setdefault("PYTHONUTF8", "1")
    env_map.setdefault("PYTHONIOENCODING", "utf-8")
    if grok_home is not None:
        env_map["GROK_HOME"] = str(Path(grok_home).resolve())
    if codex_home is not None:
        env_map["CODEX_HOME"] = str(Path(codex_home).resolve())
    return env_map


def codex_provider_argv(cfg: LlmConfig) -> list[str]:
    """Cindy 式 -c model_provider：base_url + env_key，默认 chat 而不是 /responses。"""
    p = CODEX_PROVIDER
    base = cfg.openai_base
    wire = codex_wire_api()
    return [
        "-c",
        f'model_provider="{p}"',
        "-c",
        f'model_providers.{p}.name="gameaihack"',
        "-c",
        f'model_providers.{p}.base_url="{base}"',
        "-c",
        f'model_providers.{p}.wire_api="{wire}"',
        "-c",
        f'model_providers.{p}.env_key="OPENAI_API_KEY"',
        "-c",
        f'model_providers.{p}.supports_websockets=false',
    ]
