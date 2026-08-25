"""Fast filesystem helpers. Path.rglob is convenient; os.walk is cheaper on big trees."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections.abc import Iterable, Iterator
from pathlib import Path

EXTRA_BIN_DIRS = (
    Path.home() / ".local" / "bin",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
)


def which_exe(*names: str) -> str | None:
    """PATH + 常见安装目录。doctor 和 Il2CppDumper 共用。"""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        for folder in EXTRA_BIN_DIRS:
            path = folder / name
            try:
                if path.is_file() and os.access(path, os.X_OK):
                    return str(path)
            except OSError:
                continue
    return None

SKIP_WALK_DIRS = {".git", "__pycache__", ".dsh"}

SO_KEEP = re.compile(
    r"(il2cpp|unity|cocos|xlua|lua|ue4|unreal|godot|mono|libmain|xxtea|encrypt|game)",
    re.I,
)


def iter_files(root: Path | str, *, skip_dirs: Iterable[str] | None = None) -> Iterator[Path]:
    root = Path(root)
    if not root.exists():
        return
    skip = {s.lower() for s in SKIP_WALK_DIRS}
    if skip_dirs:
        skip.update(s.lower() for s in skip_dirs)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if skip:
            dirnames[:] = [d for d in dirnames if d.lower() not in skip]
        base = Path(dirpath)
        for name in filenames:
            yield base / name


def rel_files(root: Path | str, *, skip_dirs: Iterable[str] | None = None) -> list[str]:
    root = Path(root)
    if not root.exists():
        return []
    root_s = str(root)
    skip = {s.lower() for s in SKIP_WALK_DIRS}
    if skip_dirs:
        skip.update(s.lower() for s in skip_dirs)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if skip:
            dirnames[:] = [d for d in dirnames if d.lower() not in skip]
        for name in filenames:
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, root_s).replace(os.sep, "/"))
    out.sort()
    return out


def count_by_suffix(root: Path | str, suffix: str) -> int:
    root = Path(root)
    if not root.is_dir():
        return 0
    suf = suffix.lower()
    n = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_WALK_DIRS and not d.startswith(".")]
        n += sum(1 for f in filenames if f.lower().endswith(suf) and not f.startswith("."))
    return n


def link_or_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dest.exists() and dest.samefile(src):
            return
    except OSError:
        pass
    if dest.exists() or dest.is_symlink():
        try:
            dest.unlink()
        except OSError:
            pass
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def sha256_path(path: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            if limit is not None and n + len(chunk) > limit:
                chunk = chunk[: max(0, limit - n)]
                h.update(chunk)
                break
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest()


def sha256_reuse(path: Path, prev: dict | None) -> tuple[str, dict]:
    """Reuse sha256 when path/size/mtime match the previous sidecar."""
    st = path.stat()
    meta = {
        "input": str(path),
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
    }
    prev = prev or {}
    if (
        prev.get("sha256")
        and prev.get("input") == meta["input"]
        and prev.get("size") == meta["size"]
        and prev.get("mtime_ns") == meta["mtime_ns"]
    ):
        meta["sha256"] = prev["sha256"]
        return str(prev["sha256"]), meta
    meta["sha256"] = sha256_path(path)
    return meta["sha256"], meta


def so_files(merged: Path) -> list[Path]:
    """libil2cpp / libunity 等，优先 arm64，避免扫遍所有 abi 和插件 so."""
    lib = merged / "lib"
    fallback: list[Path] = []
    for abi in ("arm64-v8a", "armeabi-v7a", "x86_64", "x86"):
        d = lib / abi
        if not d.is_dir():
            continue
        all_so = [p for p in d.glob("*.so") if p.is_file()]
        hits = [p for p in all_so if SO_KEEP.search(p.name)]
        if hits:
            return hits
        if all_so and not fallback:
            fallback = all_so
    if fallback:
        return fallback
    out: list[Path] = []
    for p in iter_files(merged):
        if p.suffix.lower() == ".so" and SO_KEEP.search(p.name):
            out.append(p)
            if len(out) >= 12:
                break
    return out


def suffixes_present(root: Path, wanted: set[str]) -> set[str]:
    found: set[str] = set()
    if not wanted or not root.exists():
        return found
    for p in iter_files(root):
        suf = p.suffix.lower()
        if suf in wanted:
            found.add(suf)
            if found == wanted:
                break
    return found


def find_named(root: Path, names: set[str], *, hints: Iterable[Path] | None = None) -> dict[str, Path]:
    want = set(names)
    found: dict[str, Path] = {}
    for h in hints or ():
        if h.is_file() and h.name in want and h.name not in found:
            found[h.name] = h
            if len(found) == len(want):
                return found
    for p in iter_files(root):
        if p.name in want and p.name not in found:
            found[p.name] = p
            if len(found) == len(want):
                break
    return found
