"""自建 agent：OpenAI 兼容 HTTP 工具循环。不调用 grok/codex CLI。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from gameaihack.agent.fs_tools import SCHEMAS, run_tool
from gameaihack.agent.llm import LlmConfig, resolve_llm
from gameaihack.agent.drivers.grok import EventGrouper
from gameaihack.agent.drivers.types import AgentError, AgentRequest
from gameaihack.core.progress import stream


def _post(cfg: LlmConfig, payload: dict, timeout: int) -> dict:
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
        with urllib.request.urlopen(req, timeout=max(timeout, 30)) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:800]
        raise AgentError(f"LLM HTTP {e.code}: {err}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AgentError(f"LLM 不可达 {cfg.chat_url}: {e}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AgentError(f"LLM 不是 JSON：{raw[:300]}") from e
    if data.get("error"):
        raise AgentError(str(data.get("error"))[:400])
    return data


def _message(choice: dict) -> dict:
    msg = (choice or {}).get("message") or {}
    return msg if isinstance(msg, dict) else {}


def _tool_calls(msg: dict) -> list:
    calls = msg.get("tool_calls") or msg.get("toolCalls") or []
    return calls if isinstance(calls, list) else []


def _text(msg: dict) -> str:
    c = msg.get("content") or msg.get("reasoning_content") or ""
    if isinstance(c, list):
        return "".join((p.get("text") or "") if isinstance(p, dict) else str(p) for p in c)
    think = msg.get("reasoning_content") or msg.get("thinking") or ""
    if think and not c:
        return ""
    return str(c or "")


def _think(msg: dict) -> str:
    t = msg.get("reasoning_content") or msg.get("thinking") or ""
    if isinstance(t, dict):
        t = t.get("text") or ""
    return str(t or "")


def run_sdk(req: AgentRequest, *, cfg: LlmConfig | None = None, via: str = "sdk") -> dict:
    cfg = cfg or resolve_llm()
    if cfg is None or not cfg.api_key:
        raise AgentError("请设 LLM_API_KEY、LLM_BASE_URL、LLM_MODELS（自定义网关即可，不需要 grok/codex CLI）。")
    model = (req.model or cfg.model or "").split(",", 1)[0].strip()
    job = req.job_dir.resolve()
    def publish(msg: str) -> None:
        stream(msg)
        if req.on_line:
            req.on_line(msg)

    grouper = EventGrouper(publish)
    sys = (
        "你是 gameaihack 自建 agent，自带文件工具，不调用 grok/codex CLI。\n"
        f"工作区：{job}\n"
        "工具：read_file / write / search_replace / list_dir / tree / glob / grep。\n"
        "先 list_dir . 和 read_file output/策划/_事实源.md、清单.md。\n"
        "看美术用 list_dir output/美术（看文件夹计数）和 美术/清单/，不要枚举上万 png。\n"
        "只能 write/search_replace output/策划/ 与 清单。不要改 raw/、_事实源.md。\n"
        "用中文。没证据标未知。"
    )
    messages: list[dict] = [
        {"role": "system", "content": sys},
        {"role": "user", "content": req.prompt},
    ]
    payload_base = {
        "model": model,
        "tools": SCHEMAS,
        "tool_choice": "auto",
        "temperature": 0.2,
        "reasoning_effort": req.effort or "xhigh",
    }
    stream(f"{via}  {model}  {cfg.openai_base}")
    n_write = 0
    turns = max(8, min(int((req.timeout or 1800) / 20), 80))
    try:
        for _ in range(turns):
            try:
                data = _post(cfg, {**payload_base, "messages": messages}, min(req.timeout, 180))
            except AgentError as e:
                if payload_base.get("reasoning_effort") and "400" in str(e):
                    payload_base.pop("reasoning_effort", None)
                    data = _post(cfg, {**payload_base, "messages": messages}, min(req.timeout, 180))
                else:
                    raise
            choices = data.get("choices") or []
            if not choices:
                raise AgentError(f"LLM 无 choices：{str(data)[:300]}")
            msg = _message(choices[0])
            think = _think(msg)
            if think:
                grouper.feed(json.dumps({"type": "thought", "data": think[:4000]}, ensure_ascii=False))
                grouper.flush_text()
            calls = _tool_calls(msg)
            content = _text(msg)
            if calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": calls,
                    }
                )
                for call in calls:
                    fn = call.get("function") or {}
                    name = str(fn.get("name") or call.get("name") or "")
                    raw_args = fn.get("arguments") or call.get("arguments") or "{}"
                    if isinstance(raw_args, dict):
                        args = raw_args
                    else:
                        try:
                            args = json.loads(raw_args or "{}")
                        except json.JSONDecodeError:
                            args = {}
                    path = str(args.get("path") or args.get("pattern") or "")
                    grouper.feed(
                        json.dumps(
                            {
                                "type": "tool_call",
                                "toolName": name,
                                "rawInput": {"path": path},
                            },
                            ensure_ascii=False,
                        )
                    )
                    out = run_tool(job, name, args if isinstance(args, dict) else {})
                    if name == "write":
                        n_write += 1
                    cid = call.get("id") or name
                    messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": out[:24000]})
                continue
            if content:
                grouper.feed(json.dumps({"type": "text", "data": content[:4000]}, ensure_ascii=False))
            grouper.close()
            if not n_write and content:
                return {"ok": False, "via": via, "text": content, "error": "模型没有调用 write 写策划文件"}
            return {"ok": True, "via": via, "text": content, "error": ""}
    except AgentError:
        grouper.close()
        raise
    grouper.close()
    return {"ok": False, "via": via, "text": "", "error": f"超过 {turns} 轮仍未结束"}


class SdkDriver:
    """自建 HTTP 工具循环。"""

    kind = "sdk"
    name = "自建 Agent"
    endpoint = "chat/completions"

    def __init__(self, via: str = "sdk"):
        self.via = via or "sdk"

    def require(self, cfg=None):
        cfg = cfg or resolve_llm()
        if cfg is None or not getattr(cfg, "api_key", None):
            raise AgentError(
                "自建 agent（--via sdk）请设 LLM_API_KEY、LLM_BASE_URL、LLM_MODELS。"
                "不需要 grok/codex CLI。本机 CLI 请用 --via grok 或 --via codex。"
            )
        return cfg

    def run(self, req: AgentRequest, *, cfg=None) -> dict:
        try:
            return run_sdk(req, cfg=cfg or resolve_llm(), via=self.via)
        except AgentError as e:
            return {"ok": False, "via": self.via, "text": "", "error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "via": self.via, "text": "", "error": f"{type(e).__name__}: {e}"}
