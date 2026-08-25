"""流水线端口。实现可以换，调用方只认这些接口。

复刻路径（主契约）：

    包 → 解开 raw/ → 抽出 output/美术 → agent（sdk / grok / codex / dsh）读 raw+美术写出 output/策划
        → 封口 复刻说明.md（策划与美术怎么对照着重做）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

STAGES = (
    "unpack",
    "fingerprint",
    "extract",
    "normalize",
    "levels",
    "design",
    "ai",
    "report",
)


def should_run(stage: str, from_stage: str | None) -> bool:
    if not from_stage:
        return True
    if from_stage not in STAGES:
        return True
    return STAGES.index(stage) >= STAGES.index(from_stage)


class JobPaths:
    """一个 job 的目录。raw 给 agent 读，output 是成品。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def raw(self) -> Path:
        from gameaihack.core.layout import raw_dir

        return raw_dir(self.root)

    @property
    def output(self) -> Path:
        from gameaihack.core.layout import output_dir

        return output_dir(self.root)

    @property
    def unpacked(self) -> Path:
        from gameaihack.core.layout import unpack_dir

        return unpack_dir(self.root)

    @property
    def merged(self) -> Path:
        return self.unpacked / "merged"

    @property
    def extract(self) -> Path:
        from gameaihack.core.layout import extract_dir

        return extract_dir(self.root)

    @property
    def ir(self) -> Path:
        from gameaihack.core.layout import ir_dir

        return ir_dir(self.root)

    @property
    def design(self) -> Path:
        from gameaihack.core.layout import design_dir

        return design_dir(self.root)

    @property
    def art(self) -> Path:
        from gameaihack.core.layout import art_dir

        return art_dir(self.root)


@runtime_checkable
class Inspector(Protocol):
    def inspect(self, src: Path, obb: list[Path], hotupdate: Path | None) -> Any:
        """包体体检：引擎猜测、输入分。"""


@runtime_checkable
class Unpacker(Protocol):
    def unpack(
        self,
        src: Path,
        dest: Path,
        obb: list[Path],
        hotupdate: Path | None,
    ) -> Any:
        """解开 APK/XAPK 到 dest（含 merged/）。"""


@runtime_checkable
class Fingerprinter(Protocol):
    def scan(self, paths: list, **kwargs: Any) -> Any:
        """引擎 / 热更 / 保护指纹。"""


@runtime_checkable
class Extractor(Protocol):
    def extract(
        self,
        merged: Path,
        dest: Path,
        fingerprint: dict,
        *,
        mode: str,
        adapters: dict | None = None,
    ) -> Any:
        """按引擎抽出配置/图音到 dest。"""


@runtime_checkable
class TableNormalizer(Protocol):
    def discover(self, norm: Path, merged: Path) -> list:
        """找出数值表。"""


@runtime_checkable
class LevelIndexer(Protocol):
    def rebuild(self, merged: Path, norm: Path, tables: list, preview_dir: Path) -> list:
        """关卡索引（能解几何就解）。"""


@runtime_checkable
class ArtRipper(Protocol):
    def rip(self, job_dir: Path, progress=None) -> int:
        """游戏贴图 → output/美术。返回张数。"""


@runtime_checkable
class DesignAgent(Protocol):
    """读 raw + 美术，写 output/策划。默认 DeepSeek Harness SDK。"""

    def require(self, via: str = "sdk") -> Any:
        """检查 agent / 模型密钥。没有就抛。"""

    def analyze(self, job_dir: Path, ir: dict, cfg: Any | None = None, via: str = "sdk") -> dict:
        """跑 agent。返回 {agent, ok, files}。交差线：核心章 + 图鉴篇。"""


@runtime_checkable
class Publisher(Protocol):
    def render(self, job_dir: Path, ir: dict, *, thumbs_only: bool, overwrite_design: bool) -> None:
        """写 output 骨架或收口（美术清单、data）。overwrite_design=False 时不覆盖 agent 策划正文，但会重写人话关卡表。"""

    def harvest(self, job_dir: Path) -> int:
        """把散落的策划收口到 output/策划。"""

    def seal(self, job_dir: Path, ir: dict) -> dict:
        """封口复刻包：复刻说明 + 完整度。不覆盖策划正文。"""
