"""DeepSeek Harness 通道：cwd 是 raw/，策划写到 ../output/策划/。"""

from __future__ import annotations

from .types import AgentError, AgentRequest


class DshDriver:
    via = "dsh"
    name = "DeepSeek Harness"
    endpoint = "dsh --profile headless"

    def require(self, cfg=None) -> list[str]:
        from gameaihack.agent.dsh import require_dsh

        argv = require_dsh()
        if cfg is None or not getattr(cfg, "api_key", None):
            raise AgentError(
                "DSH 需要模型密钥。请设 LLM_API_KEY、LLM_BASE_URL、LLM_MODELS（与 llm_bench 相同）。"
            )
        return argv

    def run(self, req: AgentRequest, *, cfg=None) -> dict:
        from gameaihack.agent.dsh import run_dsh

        self.require(cfg)
        return run_dsh(
            req.job_dir,
            req.prompt,
            cfg,
            timeout=req.timeout,
            on_line=req.on_line,
        )
