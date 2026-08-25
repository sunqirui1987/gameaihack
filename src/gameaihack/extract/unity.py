from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from gameaihack.core.fs import find_named, iter_files
from gameaihack.extract.base import KIND_DIR, ExtractItem, ExtractReport, sha256_bytes, sha256_path

UNITY_GLOBS = [
    "assets/bin/Data",
    "assets/aa",
    "assets/AssetBundles",
]
UNITY_SUF = {"", ".assets", ".resource", ".ress", ".bundle", ".unity3d", ".dat"}
# 服装/头像等大 bundle 由 art ripper 抽图，这里不再 UnityPy.load。
_ARTISH = re.compile(
    r"(costume|avatar|mannequin|propbundle|frameatlas|_frames|offericon|seasonpass)",
    re.I,
)
_SKIP_EXPORT = {"Texture2D", "Sprite"}


def _unity_files(merged: Path) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for base in UNITY_GLOBS:
        p = merged.joinpath(*base.split("/"))
        if p.is_dir():
            for f in iter_files(p):
                if f.suffix.lower() not in UNITY_SUF:
                    continue
                if _ARTISH.search(f.name):
                    continue
                try:
                    if f.stat().st_size < 256:
                        continue
                except OSError:
                    continue
                if f not in seen:
                    seen.add(f)
                    out.append(f)
        elif p.is_file() and p not in seen:
            try:
                if p.stat().st_size < 256:
                    continue
            except OSError:
                continue
            seen.add(p)
            out.append(p)
    assets = merged / "assets"
    if assets.is_dir():
        for f in assets.iterdir():
            if f.is_file() and f.suffix.lower() in {".bundle", ".unity3d", ".assets"}:
                if _ARTISH.search(f.name):
                    continue
                try:
                    if f.stat().st_size < 256:
                        continue
                except OSError:
                    continue
                if f not in seen:
                    seen.add(f)
                    out.append(f)
    return out


def extract_unity(merged: Path, dest: Path, *, max_files: int = 2500) -> ExtractReport:
    report = ExtractReport(adapter="unity")
    files = _unity_files(merged)
    report.discovered = len(files)
    if not files:
        return report
    try:
        import UnityPy  # type: ignore
    except ImportError:
        report.warnings.append("unitypy_not_installed")
        return report

    dest.mkdir(parents=True, exist_ok=True)
    exported = 0
    for container in files:
        rel = container.relative_to(merged).as_posix()
        try:
            env = UnityPy.load(str(container))
        except Exception as e:  # noqa: BLE001 — 坏容器很常见
            report.warnings.append(f"unity_load_fail:{rel}:{type(e).__name__}")
            continue
        try:
            objects = list(env.objects)
        except Exception as e:  # noqa: BLE001
            report.warnings.append(f"unity_objects_fail:{rel}:{type(e).__name__}")
            continue
        for obj in objects:
            if exported >= max_files:
                report.warnings.append("unity_export_capped")
                return report
            try:
                tname = obj.type.name if hasattr(obj.type, "name") else str(obj.type)
            except Exception:
                continue
            if tname in _SKIP_EXPORT:
                continue
            try:
                item = _export_obj(obj, tname, dest, rel)
            except Exception:
                continue
            if item:
                report.items.append(item)
                exported += 1
    boot = merged / "assets/bin/Data/boot.config"
    if boot.exists():
        text = boot.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if "unityVersion" in line or line.lower().startswith("build-guid"):
                report.extra.setdefault("boot", []).append(line.strip())
    dump_note = try_il2cpp_dumper(merged, dest.parent / "raw")
    if dump_note:
        report.warnings.append(dump_note)
    rip = try_asset_ripper(merged, dest.parent / "raw")
    if rip:
        report.warnings.append(rip)
    return report


def try_il2cpp_dumper(merged: Path, raw_dir: Path) -> str | None:
    """若 PATH 上有 Il2CppDumper，尝试产出 dummy dll。失败只记警告。"""
    found = find_named(
        merged,
        {"libil2cpp.so", "global-metadata.dat"},
        hints=(
            merged / "lib" / "arm64-v8a" / "libil2cpp.so",
            merged / "lib" / "armeabi-v7a" / "libil2cpp.so",
            merged / "assets" / "bin" / "Data" / "global-metadata.dat",
        ),
    )
    so = found.get("libil2cpp.so")
    meta = found.get("global-metadata.dat")
    if not so or not meta:
        return None
    from gameaihack.core.fs import which_exe

    exe = which_exe("Il2CppDumper", "il2cppdumper")
    if not exe:
        return "il2cppdumper_not_on_path"
    out = raw_dir / "il2cpp"
    out.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([exe, str(so), str(meta), str(out)], timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"il2cppdumper:{e}"
    return None


def try_asset_ripper(merged: Path, raw_dir: Path) -> str | None:
    exe = shutil.which("AssetRipper") or shutil.which("assetripper")
    if not exe:
        return None
    data = merged / "assets/bin/Data"
    if not data.exists():
        return None
    out = raw_dir / "assetripper"
    out.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([exe, str(data), "-o", str(out)], timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"assetripper:{e}"
    return None


def _export_obj(obj, tname: str, dest: Path, container: str) -> ExtractItem | None:
    # Texture2D / Sprite 由 art ripper 抽，这里只取文本/音频/脚本。
    kind_map = {
        "AudioClip": "audio",
        "TextAsset": "config",
        "MonoBehaviour": "config",
    }
    kind = kind_map.get(tname)
    if not kind:
        return None
    name = f"{tname}_{getattr(obj, 'path_id', 'x')}"
    meta: dict = {"unity_type": tname, "container": container}
    folder = KIND_DIR.get(kind, "misc")

    if tname == "AudioClip":
        data = obj.read()
        name = getattr(data, "name", None) or name
        samples = getattr(data, "samples", None) or {}
        if not samples:
            return None
        aname, payload = next(iter(samples.items()))
        path = dest / folder / f"{_safe(aname)}"
        if not path.suffix:
            path = path.with_suffix(".wav")
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = payload if isinstance(payload, (bytes, bytearray)) else bytes(payload)
        path.write_bytes(raw)
        return _item("audio", aname, container, path, dest, "unitypy", meta, sha=sha256_bytes(raw), nbytes=len(raw))

    if tname == "TextAsset":
        data = obj.read()
        name = getattr(data, "name", None) or name
        script = getattr(data, "script", None)
        raw = script.encode("utf-8", "replace") if isinstance(script, str) else (script or b"")
        if not isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw)
        path = dest / folder / "textassets" / f"{_safe(name)}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return _item("config", name, container, path, dest, "unitypy", meta, sha=sha256_bytes(raw), nbytes=len(raw))

    if tname == "MonoBehaviour":
        try:
            tree = obj.read_typetree()
        except Exception:
            return None
        if not isinstance(tree, dict):
            return None
        name = str(tree.get("m_Name") or name)
        import json

        path = dest / folder / "monobehaviour" / f"{_safe(name)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
        meta["fields"] = list(tree.keys())[:40]
        return _item("config", name, container, path, dest, "unitypy", meta)
    return None


def _safe(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:80]
    return keep or "unnamed"


def _item(kind, name, original, path: Path, dest: Path, extractor, meta, *, sha: str | None = None, nbytes: int | None = None) -> ExtractItem:
    return ExtractItem(
        kind=kind,
        name=str(name),
        original_path=original,
        export_rel=path.relative_to(dest).as_posix(),
        sha256=sha or sha256_path(path),
        bytes=nbytes if nbytes is not None else path.stat().st_size,
        extractor=extractor,
        meta=meta,
    )
