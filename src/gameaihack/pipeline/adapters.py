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
    """读 raw/ 和 output/美术/，写 output/策划/。通道 sdk / grok / codex / dsh。"""

    def require(self, via: str = "sdk") -> Any:
        from gameaihack.agent.drivers import resolve_driver
        from gameaihack.agent.llm import resolve_llm

        cfg = resolve_llm()
        resolve_driver(via).require(cfg)
        return cfg

    def analyze(self, job_dir: Path, ir: dict, cfg: Any | None = None, via: str = "sdk") -> dict:
        from gameaihack.agent.book import run_ai_analysis

        return run_ai_analysis(job_dir, ir, cfg=cfg, via=via)


DshDesignAgent = LlmDesignAgent


class DefaultPublisher:
    def render(self, job_dir: Path, ir: dict, *, thumbs_only: bool, overwrite_design: bool) -> None:
        from gameaihack.publish.report import render_deliverable

        render_deliverable(job_dir, ir, thumbs_only=thumbs_only, overwrite_design=overwrite_design)

    def harvest(self, job_dir: Path) -> int:
        from gameaihack.publish.projects import harvest_dsh

        return harvest_dsh(job_dir)

    def seal(self, job_dir: Path, ir: dict) -> dict:
        from gameaihack.publish.kit import seal_kit

        return seal_kit(job_dir, ir)


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
