"""默认适配器：把现有模块挂到 ports 上。换实现只改这里。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class DefaultInspector:
    def inspect(self, src: Path, obb: list[Path], hotupdate: Path | None) -> Any:
        from gameaihack.ingest.inspect import inspect_input

        return inspect_input(src, obb, hotupdate)


class DefaultUnpacker:
    def unpack(self, src: Path, dest: Path, obb: list[Path], hotupdate: Path | None) -> Any:
        from gameaihack.ingest import unpack_to

        return unpack_to(src, dest, obb, hotupdate)


class DefaultFingerprinter:
    def scan(self, paths: list, **kwargs: Any) -> Any:
        from gameaihack.fingerprint import scan_paths

        return scan_paths(paths, **kwargs)


class DefaultExtractor:
    def extract(
        self,
        merged: Path,
        dest: Path,
        fingerprint: dict,
        *,
        mode: str,
        adapters: dict | None = None,
    ) -> Any:
        from gameaihack.extract import run_extract

        return run_extract(merged, dest, fingerprint, mode=mode, adapters=adapters)


class DefaultTableNormalizer:
    def discover(self, norm: Path, merged: Path) -> list:
        from gameaihack.content.tables import discover_tables

        return discover_tables(norm, merged)


class DefaultLevelIndexer:
    def rebuild(self, merged: Path, norm: Path, tables: list, preview_dir: Path) -> list:
        from gameaihack.content.levels import rebuild_levels

        return rebuild_levels(merged, norm, tables, preview_dir)


class DefaultArtRipper:
    def rip(self, job_dir: Path, progress=None) -> int:
        from gameaihack.art.unity import ensure_game_art

        return ensure_game_art(job_dir, progress=progress)


class LlmDesignAgent:
    """提取策划与美术，再用 Maker 做成玩法一模一样的新游戏。"""

    def require(self, via: str = "sdk") -> Any:
        from gameaihack.agent.drivers import resolve_driver
        from gameaihack.agent.llm import resolve_llm

        cfg = resolve_llm()
        resolve_driver(via).require(cfg)
        return cfg

    def analyze(self, job_dir: Path, ir: dict, cfg: Any | None = None, via: str = "sdk") -> dict:
        from gameaihack.agent.run import run_ai_analysis

        return run_ai_analysis(job_dir, ir, cfg=cfg, via=via)


DshDesignAgent = LlmDesignAgent


class DefaultPublisher:
    def harvest(self, job_dir: Path) -> int:
        from gameaihack.publish.kit import harvest_design

        return harvest_design(job_dir)

    def seal(self, job_dir: Path, ir: dict) -> dict:
        from gameaihack.publish.kit import seal_kit
        from gameaihack.publish.maker import emit_maker_project

        snap = seal_kit(job_dir, ir)
        emit_maker_project(job_dir, ir)
        return snap


def default_ports() -> dict:
    """编排只拿这一套端口。换实现：子类或换这里的实例。"""
    return {
        "unpacker": DefaultUnpacker(),
        "fingerprinter": DefaultFingerprinter(),
        "extractor": DefaultExtractor(),
        "tables": DefaultTableNormalizer(),
        "levels": DefaultLevelIndexer(),
        "art": DefaultArtRipper(),
        "agent": LlmDesignAgent(),
        "publisher": DefaultPublisher(),
    }
