#!/usr/bin/env python3
"""生成自制黄金样本 APK（不含商业包）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.helpers import rich_game_files, write_zip  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests/fixtures/golden.apk"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_zip(out, rich_game_files(out.parent))
    print(out)


if __name__ == "__main__":
    main()
