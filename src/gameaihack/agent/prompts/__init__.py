"""分析 agent 的提示词。全仓库只认 mission.py 这一份任务文案。"""

from .drive import drive_tasks, gap_prompt
from .mission import (
    CONSTRAINTS,
    DRIVE,
    GOAL,
    HOW_TO_REMAKE,
    INIT_CMD,
    INSTALL_CMD,
    JOB_AGENTS,
    PERSONA,
    PLAY_PRD,
    PRD_NEEDLES,
    RAW_AGENTS,
    job_readme,
    output_agents,
    output_readme,
)
from .workspace import write_workspace_agents

__all__ = [
    "CONSTRAINTS",
    "DRIVE",
    "GOAL",
    "HOW_TO_REMAKE",
    "INIT_CMD",
    "INSTALL_CMD",
    "JOB_AGENTS",
    "PERSONA",
    "PLAY_PRD",
    "PRD_NEEDLES",
    "RAW_AGENTS",
    "drive_tasks",
    "gap_prompt",
    "job_readme",
    "output_agents",
    "output_readme",
    "write_workspace_agents",
]
