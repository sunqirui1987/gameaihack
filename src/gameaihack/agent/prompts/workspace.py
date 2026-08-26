"""把统一任务文案写进 job / raw。"""

from __future__ import annotations

from pathlib import Path

from gameaihack.agent.prompts.mission import JOB_AGENTS, RAW_AGENTS
from gameaihack.core.layout import raw_dir


def write_workspace_agents(job_dir: Path) -> None:
    job_dir = Path(job_dir)
    (job_dir / "AGENTS.md").write_text(JOB_AGENTS, encoding="utf-8")
    raw = raw_dir(job_dir)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "AGENTS.md").write_text(RAW_AGENTS, encoding="utf-8")
