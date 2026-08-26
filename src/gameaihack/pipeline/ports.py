"""流水线端口。实现可以换，调用方只认这些接口。

复刻路径（主契约）：

    包 → 机器解开 raw/
        → agent 反编译玩法，写进 TapTap Maker 工程 output/
           （assets/ 资源 + 策划/ 玩法 + scripts/ 能玩的游戏）
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

    @property
    def assets(self) -> Path:
        from gameaihack.core.layout import assets_dir

        return assets_dir(self.root)


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
        """提取美术 → output/assets/。返回文件数。"""


@runtime_checkable
class DesignAgent(Protocol):
    """提取策划 PRD，并在 Maker 里做成同一套游戏。"""

    def require(self, via: str = "sdk") -> Any:
        """检查 agent / 模型密钥。没有就抛。"""

    def analyze(self, job_dir: Path, ir: dict, cfg: Any | None = None, via: str = "sdk") -> dict:
        """跑 agent。交差：PRD + assets + scripts/main.lua。"""


@runtime_checkable
class Publisher(Protocol):
    def harvest(self, job_dir: Path) -> int:
        """把散落的策划收口到 output/策划。"""

    def seal(self, job_dir: Path, ir: dict) -> dict:
        """封口：完整度 + Maker init。不覆盖策划正文和已有 Lua。"""
