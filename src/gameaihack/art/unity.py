"""从 Unity bundle / unity3d / asset 抽出 Texture2D / Sprite PNG 到 game/美术。"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

SAFE = re.compile(r"[^A-Za-z0-9._\u4e00-\u9fff-]+")
SKIP_NAME = re.compile(
    r"(normalmap|_n$|_n_|_mask|metallic|occlusion|\blut\b|noise|dummy|"
    r"unity.?default|monoscript|bumpmap|_m$|_ao$|sdf.?atlas)",
    re.I,
)
SKIP_FILE = re.compile(r"(monoscript|unitybuiltin|musictrack)", re.I)

BUCKET_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"costume", re.I), "服装"),
    (re.compile(r"mannequin", re.I), "角色"),
    (re.compile(r"avatar|portrait", re.I), "头像"),
    (re.compile(r"frameatlas|_frames", re.I), "头像框"),
    (re.compile(r"window", re.I), "界面"),
    (re.compile(r"offericon|offer", re.I), "礼包"),
    (re.compile(r"reward", re.I), "奖励"),
    (re.compile(r"seasonpass", re.I), "赛季"),
    (re.compile(r"clan", re.I), "公会"),
    (re.compile(r"chapter", re.I), "关卡"),
]

PROP_THEME = re.compile(r"propbundle_([a-z0-9]+)", re.I)
PACK_PREFIX = re.compile(r"(?i)^(assets/content/|assets/|packages/com\.[^/]+/)")


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
    return rip_unity_art(merged, art_dir(job_dir), progress=progress)


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
        proc = subprocess.Popen(
            [py, str(script), str(merged), str(dest)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
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
    import os

    try:
        return max(50, int(os.environ.get("GAMEAIHACK_ART_CAP", "8000")))
    except ValueError:
        return 8000


def _bucket_for(src: Path) -> str:
    name = src.name
    m = PROP_THEME.search(name)
    if m:
        return f"场景/{_safe(m.group(1), 40)}"
    for pat, bucket in BUCKET_RULES:
        if pat.search(name):
            return bucket
    return "其他"


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
    files: list[Path] = []
    aa = merged / "assets" / "aa" / "Android"
    if aa.is_dir():
        files += [p for p in aa.glob("*.bundle") if p.is_file()]
    assets = merged / "assets"
    if assets.is_dir():
        for p in assets.iterdir():
            if p.is_file() and p.suffix.lower() in {".unity3d", ".asset", ""}:
                if p.name.endswith(".manifest"):
                    continue
                files.append(p)
        packing = assets / "bin" / "Data"
        if packing.is_dir():
            for name in ("data.unity3d", "datapack.unity3d"):
                p = packing / name
                if p.is_file():
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
        uniq.append(f)
    uniq.sort(key=_priority)
    return uniq


def _safe(s: str, n: int = 80) -> str:
    t = SAFE.sub("_", s).strip("._")
    return (t or "tex")[:n]


def _out_from_container(dest: Path, bucket: str, container: str, fallback: str) -> Path:
    rel = container.replace("\\", "/")
    while True:
        m = PACK_PREFIX.match(rel)
        if not m:
            break
        rel = rel[m.end() :]
    parts = [p for p in rel.split("/") if p and p not in {".", ".."}]
    low_parts = [p.lower() for p in parts]
    if "sets" in low_parts:
        i = low_parts.index("sets")
        parts = parts[i + 1 :]
        if len(parts) >= 2 and parts[-2].lower() in {"final", "upgraded"}:
            parts = parts[:-2] + [parts[-1]]
    for skip in ("mannequins", "portraits", "sprites"):
        if skip in low_parts:
            i = low_parts.index(skip)
            parts = parts[i + 1 :]
            break
    if not parts:
        parts = [fallback]
    stem = Path(parts[-1]).stem
    sub = [_safe(p, 40) for p in parts[:-1]] + [_safe(stem) + ".png"]
    return dest / bucket / Path(*sub)


def _rip(merged: Path, dest: Path, progress=None) -> int:
    import UnityPy

    def emit(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
        if progress:
            progress(msg)

    files = _collect_files(merged)
    emit(f"[art] 容器 {len(files)} 个")
    n = 0
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for src in files:
        bucket = _bucket_for(src)
        top = bucket.split("/", 1)[0]
        cap = _per_bucket_cap()
        if counts.get(top, 0) >= cap:
            continue
        try:
            env = UnityPy.load(str(src))
        except Exception as e:
            emit(f"[art] 跳过 {src.name}: {type(e).__name__}")
            continue
        added = 0
        for container, obj in _iter_tex(env):
            if counts.get(top, 0) >= cap:
                break
            try:
                data = obj.read()
                img = getattr(data, "image", None)
                if img is None:
                    continue
                w, h = img.size
                if w < 32 or h < 32:
                    continue
                name = (
                    getattr(data, "m_Name", None)
                    or getattr(data, "name", None)
                    or str(obj.path_id)
                )
                name = str(name)
                if SKIP_NAME.search(name):
                    continue
                if container:
                    out = _out_from_container(dest, bucket, container, name)
                else:
                    out = dest / bucket / f"{_safe(name)}.png"
                key = str(out.relative_to(dest)).lower()
                if key in seen:
                    continue
                if out.exists():
                    seen.add(key)
                    continue
                i = 1
                while out.exists():
                    out = out.with_name(f"{out.stem}_{i}{out.suffix}")
                    i += 1
                out.parent.mkdir(parents=True, exist_ok=True)
                img.save(str(out))
                seen.add(str(out.relative_to(dest)).lower())
                n += 1
                added += 1
                counts[top] = counts.get(top, 0) + 1
            except Exception:
                continue
        emit(f"[art] {src.name} +{added}  累计 {n}")
    print(f"COUNT={n}", flush=True)
    return n


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
    _rip(Path(sys.argv[1]), Path(sys.argv[2]))
