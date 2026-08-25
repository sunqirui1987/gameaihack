"""jobs/<包名>/raw 与 output/ 的路径约定。

raw/     解包与中间产物，给模型读，不外发。
output/  最终成品：策划 + 抽出的美术。
"""

from __future__ import annotations

import shutil
from pathlib import Path


def raw_dir(job_dir: Path) -> Path:
    raw = job_dir / "raw"
    if (raw / "unpacked").exists() or (raw / "extract").exists() or (raw / "ir").exists():
        return raw
    if (job_dir / "unpacked").exists() or (job_dir / "extract").exists():
        return job_dir
    return raw


def output_dir(job_dir: Path) -> Path:
    """最终成品目录。旧 job 若只有 game/ 则先迁到 output/。"""
    migrate_game_to_output(job_dir)
    return job_dir / "output"


def game_dir(job_dir: Path) -> Path:
    """成品目录，等同 output/。"""
    return output_dir(job_dir)


def migrate_game_to_output(job_dir: Path) -> Path:
    """把旧的 game/ 收口成 output/。"""
    game = job_dir / "game"
    out = job_dir / "output"
    if game.is_dir() and game.resolve() != out.resolve():
        if not out.exists():
            game.rename(out)
        else:
            _merge_tree(game, out)
            shutil.rmtree(game, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    return out


# output/ 是 TapTap Maker 工程。重跑时这些目录要留（init 很慢）。
MAKER_KEEP = (
    "美术",
    "assets",
    "scripts",
    "engine-docs",
    "examples",
    "templates",
    "urhox-libs",
    "schemas",
    "tools",
    ".project",
    ".emmylua",
    ".claude",
    ".codex",
    ".cursor",
    ".gemini",
)


def reset_output(job_dir: Path, *, keep: tuple[str, ...] | None = None) -> Path:
    """每次重跑清空 output/。默认留美术和已 init 的 Maker 工程目录；策划/说明全部删掉。"""
    if keep is None:
        keep = MAKER_KEEP
    out = output_dir(job_dir)
    keep_set = set(keep)
    if out.is_dir():
        for item in list(out.iterdir()):
            if item.name in keep_set:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError:
                continue
    out.mkdir(parents=True, exist_ok=True)
    design = out / "策划"
    if design.exists():
        shutil.rmtree(design, ignore_errors=True)
    design.mkdir(parents=True, exist_ok=True)
    (out / "美术").mkdir(parents=True, exist_ok=True)
    return out


def _merge_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            _merge_tree(item, target)
        elif not target.exists():
            shutil.copy2(item, target)


def unpack_dir(job_dir: Path) -> Path:
    return raw_dir(job_dir) / "unpacked"


def extract_dir(job_dir: Path) -> Path:
    return raw_dir(job_dir) / "extract"


def ir_dir(job_dir: Path) -> Path:
    return raw_dir(job_dir) / "ir"


def design_dir(job_dir: Path) -> Path:
    return output_dir(job_dir) / "策划"


def art_dir(job_dir: Path) -> Path:
    return output_dir(job_dir) / "美术"
