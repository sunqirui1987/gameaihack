from __future__ import annotations

import os
from pathlib import Path


def configs_dir() -> Path:
    env = os.environ.get("GAMEAIHACK_CONFIGS")
    if env:
        p = Path(env)
        if (p / "fingerprint_rules.yaml").exists():
            return p
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "configs",
        Path.cwd() / "configs",
        here.parents[1] / "data",
    ]
    for cand in candidates:
        if (cand / "fingerprint_rules.yaml").exists():
            return cand
    raise FileNotFoundError(
        "找不到 configs/fingerprint_rules.yaml。请在仓库根目录运行，或设置 GAMEAIHACK_CONFIGS。"
    )


def load_yaml(name: str) -> dict:
    import yaml

    path = configs_dir() / name
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def templates_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "templates"
