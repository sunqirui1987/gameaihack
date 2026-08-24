"""流水线：只认 ports，默认实现在 adapters。"""

from gameaihack.pipeline.ports import STAGES, JobPaths, should_run
from gameaihack.pipeline.run import analyze

__all__ = ["STAGES", "JobPaths", "should_run", "analyze"]
