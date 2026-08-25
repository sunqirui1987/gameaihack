"""子进程：写 prompt、按行读 stdout、超时杀掉。"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def write_prompt_file(text: str, *, directory: str | Path | None = None) -> Path:
    folder = Path(directory) if directory else Path(tempfile.mkdtemp(prefix="gameaihack-"))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "prompt.txt"
    path.write_text(text or "", encoding="utf-8")
    return path


def kill_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()


def iter_process_lines(
    argv: list[str],
    *,
    timeout: int,
    cwd: str | Path | None = None,
    env: dict | None = None,
    stdin_text: str | None = None,
    on_line: Callable[[str], None] | None = None,
    popen=subprocess.Popen,
    use_pty: bool = False,
) -> Iterator[str]:
    if (
        use_pty
        and stdin_text is None
        and popen is subprocess.Popen
        and os.name == "posix"
    ):
        yield from _iter_pty_lines(
            argv, timeout=timeout, cwd=cwd, env=env, on_line=on_line
        )
        return
    proc = popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    assert proc.stdout is not None
    if stdin_text is not None and proc.stdin is not None:
        proc.stdin.write(stdin_text)
        proc.stdin.close()
    t0 = time.time()
    chunks: list[str] = []
    try:
        while True:
            line = proc.stdout.readline()
            if line:
                text = line.rstrip("\n")
                chunks.append(text)
                if on_line and text:
                    try:
                        on_line(text)
                    except Exception:
                        pass
                yield text
                continue
            if proc.poll() is not None:
                rest = proc.stdout.read() or ""
                for ln in rest.splitlines():
                    chunks.append(ln)
                    if on_line and ln:
                        try:
                            on_line(ln)
                        except Exception:
                            pass
                    yield ln
                break
            if time.time() - t0 > max(int(timeout), 1):
                kill_group(proc)
                raise TimeoutError(f"进程超时 {timeout}s: {' '.join(argv[:6])}")
            time.sleep(0.05)
        code = proc.wait(timeout=5)
    except TimeoutError:
        kill_group(proc)
        raise
    except subprocess.TimeoutExpired:
        kill_group(proc)
        raise TimeoutError(f"进程结束等待超时: {' '.join(argv[:6])}")
    finally:
        if proc.poll() is None:
            kill_group(proc)
    if code:
        err = "\n".join(chunks)[-800:] or " ".join(argv[:8])
        raise RuntimeError(f"进程退出 {code}: {err}")


def _iter_pty_lines(
    argv: list[str],
    *,
    timeout: int,
    cwd: str | Path | None,
    env: dict | None,
    on_line: Callable[[str], None] | None,
) -> Iterator[str]:
    """管道会让 grok 把 NDJSON 攒到结束才吐。PTY 才能一行行滚。"""
    import pty
    import select

    master, slave = pty.openpty()
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged.setdefault("TERM", "dumb")
    try:
        proc = subprocess.Popen(
            argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=str(cwd) if cwd else None,
            env=merged,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        os.close(master)
        os.close(slave)
        raise
    os.close(slave)
    buf = ""
    chunks: list[str] = []
    t0 = time.time()

    def emit(text: str) -> None:
        chunks.append(text)
        if on_line and text:
            try:
                on_line(text)
            except Exception:
                pass

    try:
        while True:
            if time.time() - t0 > max(int(timeout), 1):
                kill_group(proc)
                raise TimeoutError(f"进程超时 {timeout}s: {' '.join(argv[:6])}")
            ready, _, _ = select.select([master], [], [], 0.1)
            if master in ready:
                try:
                    data = os.read(master, 8192)
                except OSError:
                    data = b""
                if not data:
                    if proc.poll() is not None:
                        break
                    continue
                buf += data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = _ANSI.sub("", line.strip("\x00"))
                    emit(line)
                    yield line
            elif proc.poll() is not None:
                break
        if buf.strip():
            rest = _ANSI.sub("", buf.strip("\x00"))
            emit(rest)
            yield rest
        code = proc.wait(timeout=5)
    except TimeoutError:
        kill_group(proc)
        raise
    except subprocess.TimeoutExpired:
        kill_group(proc)
        raise TimeoutError(f"进程结束等待超时: {' '.join(argv[:6])}")
    finally:
        try:
            os.close(master)
        except OSError:
            pass
        if proc.poll() is None:
            kill_group(proc)
    if code:
        err = "\n".join(chunks)[-800:] or " ".join(argv[:8])
        raise RuntimeError(f"进程退出 {code}: {err}")
