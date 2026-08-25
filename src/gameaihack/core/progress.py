"""全程日志：stderr 实时打，同时写入已绑定的 job 日志文件。"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

_sinks: ContextVar[tuple[Path, ...]] = ContextVar("gameaihack_log_sinks", default=())
_file_lock = threading.Lock()


def bind_file(path: Path):
    """之后的 log() 都会追加到 path。返回 token，结束时 unbind。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return _sinks.set(_sinks.get() + (path,))


def unbind(token) -> None:
    if token is not None:
        _sinks.reset(token)


def log(msg: str) -> None:
    line = msg.rstrip("\n")
    if not line:
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = f"{ts}  {line}"
    sys.stderr.write(out + "\n")
    sys.stderr.flush()
    _append_file(out)


def stream(msg: str) -> None:
    """Agent 实时输出：控制台不打时间戳，接近 grok/codex CLI。"""
    line = msg.rstrip("\n")
    if not line:
        return
    sys.stderr.write(line + "\n")
    sys.stderr.flush()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _append_file(f"{ts}  {line}")


def _append_file(out: str) -> None:
    with _file_lock:
        for path in _sinks.get():
            try:
                with path.open("a", encoding="utf-8") as f:
                    f.write(out + "\n")
            except OSError:
                continue


def log_exception(prefix: str = "异常") -> None:
    log(f"{prefix}:\n{traceback.format_exc().rstrip()}")


def bar(got: int, total: int | None, *, prefix: str = "", t0: float | None = None) -> None:
    elapsed = max((time.time() - t0) if t0 else 0.01, 0.01)
    speed = got / elapsed
    if total and total > 0:
        pct = min(100.0, got * 100.0 / total)
        width = 22
        fill = int(width * pct / 100)
        meter = "█" * fill + "░" * (width - fill)
        line = f"\r  {prefix}  {_mb(got)}/{_mb(total)} MB  {pct:5.1f}%  {meter}  {_mb(speed)} MB/s"
    else:
        line = f"\r  {prefix}  {_mb(got)} MB    {_mb(speed)} MB/s"
    sys.stderr.write(line)
    sys.stderr.flush()


def bar_done() -> None:
    sys.stderr.write("\n")
    sys.stderr.flush()


def _mb(n: float) -> str:
    return f"{n / (1024 * 1024):.1f}"
