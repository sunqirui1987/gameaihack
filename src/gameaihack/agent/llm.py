"""LLM 接入，读法对齐 llm_bench：LLM_API_KEY / LLM_BASE_URL / LLM_MODELS。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


def load_project_env() -> None:
    """读 cwd 与仓库根的 .env，不覆盖已经在环境里的变量。"""
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / ".env",
        here.parents[3] / ".env",
    ]
    seen: set[Path] = set()
    for path in candidates:
        try:
            path = path.resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        _apply_dotenv(path)


def _apply_dotenv(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] in "\"'" and value[-1:] == value[0]:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def env(*names: str, default: str = "") -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return default


load_project_env()


@dataclass
class LlmConfig:
    api_key: str
    base_url: str
    model: str
    source: str

    @property
    def chat_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/v1/chat/completions"

    @property
    def openai_base(self) -> str:
        """给 DSH / OpenAI SDK 用的根，带 /v1。"""
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return base


def resolve_llm() -> LlmConfig | None:
    load_project_env()
    key = env("LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY")
    if not key:
        return None
    base = env(
        "LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "DEEPSEEK_BASE_URL",
        default="https://api.openai.com",
    )
    model = env("LLM_MODELS", "LLM_MODEL", "DSH_MODEL", "OPENAI_MODEL", default="grok-4.6")
    if "," in model:
        model = model.split(",", 1)[0].strip()
    source = "LLM_API_KEY" if env("LLM_API_KEY") else (
        "OPENAI_API_KEY" if env("OPENAI_API_KEY") else "DEEPSEEK_API_KEY"
    )
    return LlmConfig(api_key=key, base_url=base, model=model, source=source)


def llm_enabled(cli_flag: bool | None = None) -> bool:
    if cli_flag is False:
        return False
    if os.environ.get("GAMEAIHACK_LLM", "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    if cli_flag is True:
        return resolve_llm() is not None
    try:
        from gameaihack.core.paths import load_yaml

        data = load_yaml("pipeline.yaml") or {}
        if (data.get("design") or {}).get("llm_enabled") is False:
            return False
    except Exception:
        pass
    return resolve_llm() is not None


def chat(
    messages: list[dict],
    *,
    cfg: LlmConfig | None = None,
    max_tokens: int = 4096,
    timeout: int = 180,
    temperature: float = 0.2,
) -> str:
    cfg = cfg or resolve_llm()
    if cfg is None:
        raise RuntimeError("没有 LLM_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY")
    payload = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        cfg.chat_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"LLM HTTP {e.code}: {err}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"LLM 不可达 {cfg.chat_url}: {e}") from e
    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM 无 choices：{raw[:300]}")
    msg = choices[0].get("message") or {}
    text = msg.get("content") or ""
    if isinstance(text, list):
        text = "".join(
            (p.get("text") or "") if isinstance(p, dict) else str(p) for p in text
        )
    if not str(text).strip():
        raise RuntimeError("LLM 返回空内容")
    return str(text).strip()
