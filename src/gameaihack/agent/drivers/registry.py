"""解析 --via，构造 driver。通道：grok / codex / dsh。工作区是 raw/。"""

from __future__ import annotations

import os

from .codex import CodexDriver
from .dsh import DshDriver
from .grok import GrokDriver
from .types import AgentError

DRIVERS = ("grok", "codex", "dsh")

VIA_ALIASES = {
    "grok": "grok",
    "grok-cli": "grok",
    "codex": "codex",
    "codex-cli": "codex",
    "dsh": "dsh",
    "deepseek": "dsh",
    "harness": "dsh",
}


def default_via() -> str:
    text = (os.environ.get("GAMEAIHACK_VIA") or os.environ.get("LLM_VIA") or "grok").strip()
    return parse_via(text)


def parse_via(value) -> str:
    text = str(value if value is not None else "grok").strip().lower() or "grok"
    if text not in VIA_ALIASES:
        raise AgentError(f"未知 --via: {value}；可选 grok / codex / dsh")
    return VIA_ALIASES[text]


def resolve_driver(
    via: str | None = None,
    *,
    grok_bin: str | None = None,
    codex_bin: str | None = None,
):
    via = parse_via(via)
    if via == "codex":
        return CodexDriver(codex_bin or os.environ.get("GAMEAIHACK_CODEX") or "codex")
    if via == "dsh":
        return DshDriver()
    return GrokDriver(grok_bin or os.environ.get("GAMEAIHACK_GROK") or "grok")
