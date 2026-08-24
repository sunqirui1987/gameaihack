from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from gameaihack.extract.base import KIND_DIR, ExtractItem, ExtractReport, sha256_path

UNITY_GLOBS = [
    "assets/bin/Data",
    "assets/aa",
    "assets/AssetBundles",
]


def _unity_files(merged: Path) -> list[Path]:
    out: list[Path] = []
    for base in UNITY_GLOBS:
        p = merged.joinpath(*base.split("/"))
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in {
                    "",
                    ".assets",
                    ".resource",
                    ".ress",
                    ".bundle",
                    ".unity3d",
                    ".dat",
                }:
                    out.append(f)
        elif p.is_file():
            out.append(p)
    for f in merged.rglob("*"):
        if f.suffix.lower() in {".bundle", ".unity3d", ".assets"}:
            if f not in out:
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
    so = next(merged.rglob("libil2cpp.so"), None)
    meta = next(merged.rglob("global-metadata.dat"), None)
    if not so or not meta:
        return None
    exe = shutil.which("Il2CppDumper") or shutil.which("il2cppdumper")
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
    kind_map = {
        "Texture2D": "texture",
        "Sprite": "sprite",
        "AudioClip": "audio",
        "TextAsset": "config",
        "Font": "font",
        "Shader": "shader",
        "AnimationClip": "anim",
        "Mesh": "mesh",
        "MonoBehaviour": "config",
    }
    kind = kind_map.get(tname)
    if not kind:
        return None
    name = f"{tname}_{getattr(obj, 'path_id', 'x')}"
    data = None
    meta: dict = {"unity_type": tname, "container": container}
    folder = KIND_DIR.get(kind, "misc")
    suffix = ".bin"
    raw: bytes | None = None

    if tname in {"Texture2D", "Sprite"}:
        data = obj.read()
        name = getattr(data, "name", None) or name
        img = getattr(data, "image", None)
        if img is None:
            return None
        path = dest / folder / f"{_safe(name)}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        suffix = ".png"
        return _item(kind, name, container, path, dest, "unitypy", meta)

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
        path.write_bytes(payload)
        return _item("audio", aname, container, path, dest, "unitypy", meta)

    if tname == "TextAsset":
        data = obj.read()
        name = getattr(data, "name", None) or name
        script = getattr(data, "script", None)
        raw = script.encode("utf-8", "replace") if isinstance(script, str) else (script or b"")
        path = dest / folder / "textassets" / f"{_safe(name)}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw if isinstance(raw, (bytes, bytearray)) else bytes(raw))
        return _item("config", name, container, path, dest, "unitypy", meta)

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


def _item(kind, name, original, path: Path, dest: Path, extractor, meta) -> ExtractItem:
    return ExtractItem(
        kind=kind,
        name=str(name),
        original_path=original,
        export_rel=path.relative_to(dest).as_posix(),
        sha256=sha256_path(path),
        bytes=path.stat().st_size,
        extractor=extractor,
        meta=meta,
    )
