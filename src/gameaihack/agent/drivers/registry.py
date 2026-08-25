"""解析 --via：两种一等模式。

- sdk / agent：自建 HTTP agent（默认，不需要 grok/codex CLI）
- grok / codex / dsh：本机 CLI，Cindy 式注入 LLM_* 到子进程
"""

from __future__ import annotations

import os

from .dsh import DshDriver
from .types import AgentError
from gameaihack.agent.sdk import SdkDriver

DRIVERS = ("sdk", "grok", "codex", "dsh")

VIA_ALIASES = {
    "sdk": "sdk",
    "agent": "sdk",
    "http": "sdk",
    "cindy": "sdk",
    "harness": "sdk",
    "grok": "grok",
    "grok-cli": "grok",
    "codex": "codex",
    "codex-cli": "codex",
    "dsh": "dsh",
    "deepseek": "dsh",
}


def default_via() -> str:
    text = (os.environ.get("GAMEAIHACK_VIA") or os.environ.get("LLM_VIA") or "sdk").strip()
    return parse_via(text)


def parse_via(value) -> str:
    text = str(value if value is not None else "sdk").strip().lower() or "sdk"
    if text not in VIA_ALIASES:
        raise AgentError(f"未知 --via: {value}；可选 sdk（自建 agent）/ grok / codex / dsh（本机 CLI）")
    return VIA_ALIASES[text]


def resolve_driver(
    via: str | None = None,
    *,
    grok_bin: str | None = None,
    codex_bin: str | None = None,
):
    via = parse_via(via)
    if via == "sdk":
        return SdkDriver(via="sdk")
    if via == "dsh":
        return DshDriver()
    if via == "codex":
        from .codex import CodexDriver

        return CodexDriver(codex_bin or os.environ.get("GAMEAIHACK_CODEX") or "codex")
    from .grok import GrokDriver

    return GrokDriver(grok_bin or os.environ.get("GAMEAIHACK_GROK") or "grok")
