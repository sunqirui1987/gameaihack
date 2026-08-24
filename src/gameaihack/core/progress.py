from __future__ import annotations

import sys
import time


def log(msg: str) -> None:
    sys.stderr.write(msg.rstrip() + "\n")
    sys.stderr.flush()


def bar(got: int, total: int | None, *, prefix: str = "", t0: float | None = None) -> None:
    elapsed = max((time.time() - t0) if t0 else 0.01, 0.01)
    speed = got / elapsed
    if total and total > 0:
        pct = min(100.0, got * 100.0 / total)
        width = 22
        fill = int(width * pct / 100)
        meter = "█" * fill + "░" * (width - fill)
        line = (
            f"\r  {prefix}  {_mb(got)}/{_mb(total)} MB  {pct:5.1f}%  {meter}  {_mb(speed)} MB/s"
        )
    else:
        line = f"\r  {prefix}  {_mb(got)} MB    {_mb(speed)} MB/s"
    sys.stderr.write(line)
    sys.stderr.flush()


def bar_done() -> None:
    sys.stderr.write("\n")
    sys.stderr.flush()


def _mb(n: float) -> str:
    return f"{n / (1024 * 1024):.1f}"
