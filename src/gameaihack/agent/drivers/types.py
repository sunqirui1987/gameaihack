"""请求通道共用对象。对齐 llm_bench 的 driver 形状。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class AgentError(Exception):
    """模型通道失败（缺密钥、缺 CLI、HTTP 错误、并发限额用尽）。"""


@dataclass
class AgentRequest:
    job_dir: Path
    prompt: str
    model: str = ""
    timeout: int = 1800
    effort: str = "xhigh"
    on_line: Callable[[str], None] | None = None
    api_key: str = ""
    base_url: str = ""
    cwd: Path | None = None  # 默认 job；需要时切到 output/


def split_messages(messages: list[dict]) -> tuple[str, str]:
    system_parts: list[str] = []
    rest: list[str] = []
    for item in messages or []:
        content = str(item.get("content") or "")
        if (item.get("role") or "user") == "system":
            if content:
                system_parts.append(content)
        elif content:
            rest.append(content)
    return "\n".join(system_parts).strip(), "\n".join(rest).strip()


def combined_prompt(messages: list[dict]) -> str:
    system, user = split_messages(messages)
    if system and user:
        return f"{system}\n\n{user}"
    return system or user


def is_retryable(err: str) -> bool:
    blob = (err or "").lower()
    return any(
        k in blob
        for k in (
            "concurrency limit",
            "rate limit",
            "please retry later",
            "too many requests",
            "429",
            "tpm",
            "overloaded",
        )
    )
