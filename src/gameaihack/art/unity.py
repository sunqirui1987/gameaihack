"""从 Unity bundle / unity3d / asset 抽出 Texture2D / Sprite PNG 到 output/美术。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SAFE = re.compile(r"[^A-Za-z0-9._\u4e00-\u9fff-]+")
SKIP_FILE = re.compile(r"(monoscript|unitybuiltin|musictrack)", re.I)
PACK_PREFIX = re.compile(r"(?i)^(assets/content/|assets/|packages/com\.[^/]+/)")
LOOSE_SUF = {".png", ".jpg", ".jpeg", ".webp", ".ogg", ".mp3", ".wav", ".mp4", ".ttf", ".otf"}
CONTAINER_SUF = {".bundle", ".unity3d", ".assets", ".resource", ".ress", ""}
STAMP_VER = 1
PNG_COMPRESS = 2
_LOAD_LOCK = threading.Lock()


def _py310() -> str | None:
    try:
        import UnityPy  # noqa: F401

        return sys.executable
    except ImportError:
        pass
    here = Path(sys.executable).parent / "python3.10"
    if here.exists():
        return str(here)
    return shutil.which("python3.10")


def ensure_game_art(job_dir: Path, *, progress=None) -> int:
    from gameaihack.core.layout import art_dir, unpack_dir

    merged = unpack_dir(job_dir) / "merged"
    if not merged.is_dir():
        return 0
    n = rip_unity_art(merged, art_dir(job_dir), progress=progress)
    from gameaihack.art.manifest import write_manifest

    write_manifest(art_dir(job_dir))
    return n


def rip_unity_art(merged: Path, dest: Path, *, progress=None) -> int:
    """抽出贴图到 dest。当前解释器没有 UnityPy 时改调 python3.10。"""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        import UnityPy  # noqa: F401

        return _rip(merged, dest, progress=progress)
    except ImportError:
        py = _py310()
        if not py:
            return 0
        script = Path(__file__).resolve()
        src_root = str(script.parents[2])
        env = os.environ.copy()
        env["PYTHONPATH"] = src_root + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(
            [py, str(script), str(merged), str(dest)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        n = 0
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            if progress and line:
                progress(line)
            if line.startswith("COUNT="):
                try:
                    n = int(line.split("=", 1)[1])
                except ValueError:
                    pass
        code = proc.wait()
        if code != 0 and n == 0:
            return 0
        return n


def _per_bucket_cap() -> int:
    try:
        return max(50, int(os.environ.get("GAMEAIHACK_ART_CAP", "8000")))
    except ValueError:
        return 8000


def _art_jobs() -> int:
    raw = os.environ.get("GAMEAIHACK_ART_JOBS")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return max(1, min(8, os.cpu_count() or 4))


def _stamp_path(dest: Path) -> Path:
    return dest / ".rip.json"


def _load_stamp(dest: Path) -> dict:
    path = _stamp_path(dest)
    if not path.is_file():
        return {"v": STAMP_VER, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"v": STAMP_VER, "files": {}}
    if data.get("v") != STAMP_VER or not isinstance(data.get("files"), dict):
        return {"v": STAMP_VER, "files": {}}
    return data


def _save_stamp(dest: Path, stamp: dict) -> None:
    try:
        _stamp_path(dest).write_text(json.dumps(stamp, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _src_sig(src: Path) -> dict:
    st = src.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _stamp_key(src: Path) -> str:
    try:
        return str(src.resolve())
    except OSError:
        return str(src)


def _save_png(img, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path), format="PNG", compress_level=PNG_COMPRESS, optimize=False)


def _bucket_for(src: Path, container: str = "", asset: str = "") -> str:
    from gameaihack.art.classify import classify_file

    return classify_file(src, container, asset) or "其他"


def _priority(src: Path) -> int:
    n = src.name.lower()
    if SKIP_FILE.search(n):
        return 99
    if "mannequin" in n or "avatar" in n:
        return 0
    if "window" in n or "offer" in n:
        return 1
    if "reward" in n or "season" in n or "clan" in n:
        return 2
    if n.startswith("propbundle"):
        return 3
    if "costume" in n:
        return 8
    if n in {"data.unity3d", "datapack.unity3d"}:
        return 9
    return 5


def _collect_files(merged: Path) -> list[Path]:
    from gameaihack.core.fs import iter_files

    files: list[Path] = []
    for folder in (
        merged / "assets" / "aa",
        merged / "assets" / "AssetBundles",
        merged / "assets" / "assetbundles",
    ):
        if folder.is_dir():
            for p in iter_files(folder):
                if p.name.endswith(".manifest"):
                    continue
                if p.is_file() and p.suffix.lower() in CONTAINER_SUF:
                    files.append(p)
    assets = merged / "assets"
    if assets.is_dir():
        for p in assets.iterdir():
            if p.is_file() and p.suffix.lower() in {".unity3d", ".assets", ".bundle", ".asset", ""}:
                if p.name.endswith(".manifest"):
                    continue
                files.append(p)
        packing = assets / "bin" / "Data"
        if packing.is_dir():
            for p in packing.iterdir():
                if not p.is_file():
                    continue
                n = p.name.lower()
                if n.endswith(".manifest") or n.endswith(".resS".lower()):
                    continue
                if p.suffix.lower() in CONTAINER_SUF or n.startswith(("sharedassets", "level", "resources", "data")):
                    files.append(p)
    uniq: list[Path] = []
    seen: set[Path] = set()
    for f in files:
        key = f.resolve()
        if key in seen:
            continue
        seen.add(key)
        if SKIP_FILE.search(f.name):
            continue
        try:
            if f.stat().st_size < 256:
                continue
        except OSError:
            continue
        uniq.append(f)
    uniq.sort(key=_priority)
    return uniq


def _safe(s: str, n: int = 80) -> str:
    t = SAFE.sub("_", s).strip("._")
    return (t or "tex")[:n]


_DROP_DIR = {"mannequins", "portraits", "sprites", "final", "upgraded"}


def _out_from_container(dest: Path, bucket: str, container: str, fallback: str) -> Path:
    rel = container.replace("\\", "/")
    while True:
        m = PACK_PREFIX.match(rel)
        if not m:
            break
        rel = rel[m.end() :]
    parts = [p for p in rel.split("/") if p and p not in {".", ".."}]
    low = [p.lower() for p in parts]
    if "sets" in low:
        parts = parts[low.index("sets") + 1 :]
    parts = [p for p in parts if p.lower() not in _DROP_DIR]
    if not parts:
        parts = [fallback]
    stem = Path(parts[-1]).stem
    sub = [_safe(p, 40) for p in parts[:-1]] + [_safe(stem) + ".png"]
    return dest / bucket / Path(*sub)


def _rip(merged: Path, dest: Path, progress=None) -> int:
    import UnityPy  # noqa: F401  — 确认本进程能 load

    def emit(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
        if progress:
            progress(msg)

    files = _collect_files(merged)
    jobs = _art_jobs()
    emit(f"[art] 容器 {len(files)} 个，并行 {jobs}")
    cap = _per_bucket_cap()
    n = 0
    counts: dict[str, int] = {}
    seen: set[str] = set()
    lock = threading.Lock()
    stamp = _load_stamp(dest)
    from gameaihack.core.fs import count_by_suffix

    reuse = count_by_suffix(dest, ".png") > 0
    waves: dict[int, list[Path]] = {}
    for src in files:
        waves.setdefault(_priority(src), []).append(src)

    def run_one(src: Path) -> tuple[str, int, str | None, bool]:
        bucket = _bucket_for(src)
        top = bucket.split("/", 1)[0]
        key = _stamp_key(src)
        try:
            sig = _src_sig(src)
        except OSError as e:
            return src.name, 0, type(e).__name__, False
        prev = (stamp.get("files") or {}).get(key) if reuse else None
        if (
            isinstance(prev, dict)
            and prev.get("size") == sig["size"]
            and prev.get("mtime_ns") == sig["mtime_ns"]
        ):
            added = int(prev.get("added") or 0)
            with lock:
                counts[top] = counts.get(top, 0) + added
            return src.name, added, None, True
        with lock:
            if counts.get(top, 0) >= cap:
                return src.name, 0, None, False
        try:
            added = _rip_container(src, dest, bucket, top, cap, counts, seen, lock)
        except Exception as e:  # noqa: BLE001
            return src.name, 0, type(e).__name__, False
        with lock:
            stamp.setdefault("files", {})[key] = {**sig, "added": added}
        return src.name, added, None, False

    for prio in sorted(waves):
        batch = waves[prio]
        workers = min(jobs, len(batch)) if jobs > 1 else 1
        if workers <= 1:
            results = [run_one(src) for src in batch]
        else:
            results = []
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(run_one, src): src for src in batch}
                for fut in as_completed(futs):
                    results.append(fut.result())
            results.sort(key=lambda r: r[0])
        for name, added, err, cached in results:
            n += added
            if err:
                emit(f"[art] 跳过 {name}: {err}")
            elif cached:
                emit(f"[art] {name} 缓存 +{added}  累计 {n}")
            else:
                emit(f"[art] {name} +{added}  累计 {n}")
        _save_stamp(dest, stamp)

    extra = _copy_loose_media(merged, dest, emit)
    n += extra
    if extra:
        emit(f"[art] 散文件 {extra}  → 原始/")

    print(f"COUNT={n}", flush=True)
    return n


def _copy_loose_media(merged: Path, dest: Path, emit) -> int:
    from gameaihack.core.fs import iter_files, link_or_copy

    n = 0
    roots = [
        merged / "assets" / "bin" / "Data" / "StreamingAssets",
        merged / "assets" / "StreamingAssets",
        merged / "assets" / "streamed",
    ]
    assets = merged / "assets"
    if assets.is_dir():
        roots.append(assets)
    for root in roots:
        if not root.exists():
            continue
        for p in iter_files(root, skip_dirs={"bin", "aa", "AssetBundles"}):
            if p.suffix.lower() not in LOOSE_SUF:
                continue
            try:
                if p.stat().st_size < 64:
                    continue
                rel = p.relative_to(merged)
            except (OSError, ValueError):
                continue
            parts = [_safe(x, 40) for x in rel.parts]
            out = dest / "原始" / Path(*parts)
            if out.exists():
                continue
            try:
                link_or_copy(p, out)
            except OSError:
                continue
            n += 1
            if n >= 4000:
                emit("[art] 散文件达到 4000，其余跳过")
                return n
    return n


def _rip_container(
    src: Path,
    dest: Path,
    bucket: str,
    top: str,
    cap: int,
    counts: dict[str, int],
    seen: set[str],
    lock: threading.Lock,
) -> int:
    import UnityPy

    if src.stat().st_size < 256:
        return 0
    with _LOAD_LOCK:
        env = UnityPy.load(str(src))
    added = 0
    for container, obj in _iter_tex(env):
        with lock:
            if counts.get(top, 0) >= cap:
                break
        try:
            if container:
                guess = _out_from_container(dest, bucket, container, Path(str(container)).stem)
                key = str(guess.relative_to(dest)).lower()
                with lock:
                    if key in seen:
                        continue
                    if guess.exists():
                        seen.add(key)
                        counts[top] = counts.get(top, 0) + 1
                        added += 1
                        continue
            data = obj.read()
            img = getattr(data, "image", None)
            if img is None:
                continue
            w, h = img.size
            if w < 16 or h < 16:
                continue
            name = (
                getattr(data, "m_Name", None)
                or getattr(data, "name", None)
                or str(obj.path_id)
            )
            name = str(name)
            from gameaihack.art.classify import drop_asset

            if drop_asset(name):
                continue
            bucket = _bucket_for(src, container or "", name)
            top = bucket.split("/", 1)[0]
            if container:
                out = _out_from_container(dest, bucket, container, name)
            else:
                out = dest / bucket / f"{_safe(name)}.png"
            key = str(out.relative_to(dest)).lower()
            claimed = None
            with lock:
                if key in seen or counts.get(top, 0) >= cap:
                    continue
                if out.exists():
                    seen.add(key)
                    counts[top] = counts.get(top, 0) + 1
                    added += 1
                    continue
                i = 1
                candidate = out
                while candidate.exists():
                    candidate = out.with_name(f"{out.stem}_{i}{out.suffix}")
                    i += 1
                claimed = candidate
                seen.add(str(claimed.relative_to(dest)).lower())
                counts[top] = counts.get(top, 0) + 1
            if claimed is None:
                continue
            try:
                _save_png(img, claimed)
            except Exception:
                with lock:
                    seen.discard(str(claimed.relative_to(dest)).lower())
                    counts[top] = max(0, counts.get(top, 0) - 1)
                continue
            added += 1
        except Exception:
            continue
    return added


def _iter_tex(env):
    seen: set[int] = set()
    container = getattr(env, "container", None)
    items = []
    if container is not None:
        try:
            items = list(container.items())
        except Exception:
            items = []
    for path, obj in items:
        try:
            if obj.type.name not in {"Texture2D", "Sprite"}:
                continue
        except Exception:
            continue
        seen.add(id(obj))
        yield str(path), obj
    try:
        objects = env.objects
    except Exception:
        return
    for obj in objects:
        if id(obj) in seen:
            continue
        try:
            if obj.type.name not in {"Texture2D", "Sprite"}:
                continue
        except Exception:
            continue
        yield None, obj


if __name__ == "__main__":
    src = str(Path(__file__).resolve().parents[2])
    if src not in sys.path:
        sys.path.insert(0, src)
    _rip(Path(sys.argv[1]), Path(sys.argv[2]))
