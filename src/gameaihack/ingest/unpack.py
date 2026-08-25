from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from gameaihack.core.globmatch import match_glob

APK_SUFFIXES = {".apk"}
CONTAINER_SUFFIXES = {".apk", ".xapk", ".apks", ".zip"}
OBB_SUFFIXES = {".obb"}


class IngestError(Exception):
    pass


@dataclass
class PackageInfo:
    name: str = "unknown.pack"
    version_name: str = ""
    version_code: int = 0
    min_sdk: int | None = None
    orientation: str = "unknown"
    permissions: list[str] = field(default_factory=list)
    source: str = "fallback"


@dataclass
class ContainerMeta:
    kind: str
    files: list[dict]
    inner_apks: list[str] = field(default_factory=list)
    inner_obbs: list[str] = field(default_factory=list)
    xapk_manifest: dict | None = None


def _is_zip(path: Path) -> bool:
    return zipfile.is_zipfile(path)


def detect_kind(path: Path) -> str:
    suf = path.suffix.lower()
    if path.is_dir():
        return "dir"
    if suf == ".xapk":
        return "xapk"
    if suf == ".apks":
        return "apks"
    if suf == ".obb":
        return "obb"
    if suf == ".apk":
        return "apk"
    if suf == ".zip":
        if _is_zip(path):
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
            if any(n.lower().endswith(".apk") for n in names):
                return "xapk"
            return "zip"
        return "zip"
    if _is_zip(path):
        return "apk"
    raise IngestError(f"无法打开为 zip/apk：{path}")


def _safe_join(root: Path, name: str) -> Path:
    if name.startswith("/") or name.startswith("\\"):
        raise IngestError(f"拒绝绝对路径 zip 条目：{name}")
    dest = (root / name).resolve()
    if not str(dest).startswith(str(root.resolve())):
        raise IngestError(f"拒绝 zip slip：{name}")
    return dest


def safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    for info in zf.infolist():
        if info.is_dir() or info.filename.endswith("/"):
            continue
        target = _safe_join(root, info.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)


def _iter_zip_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        return [n.replace("\\", "/") for n in z.namelist() if not n.endswith("/")]


def pick_base_apk(names: list[str]) -> str | None:
    apks = [n for n in names if n.lower().endswith(".apk")]
    if not apks:
        return None
    for n in apks:
        stem = Path(n).name.lower()
        if stem == "base.apk" or stem.startswith("base."):
            return n
    apks.sort(key=lambda n: (0 if "config." in Path(n).name.lower() else 1, len(n)))
    non_config = [n for n in apks if not Path(n).name.lower().startswith("config.")]
    return (non_config or apks)[0]


def read_xapk_manifest(path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(path) as z:
            for cand in ("manifest.json", "Manifest.json"):
                if cand in z.namelist():
                    return json.loads(z.read(cand).decode("utf-8"))
    except (OSError, json.JSONDecodeError, zipfile.BadZipFile):
        return None
    return None


def _pkg_from_dict(d: dict) -> PackageInfo:
    try:
        code = int(d.get("version_code") or 0)
    except (TypeError, ValueError):
        code = 0
    return PackageInfo(
        name=d.get("name") or "unknown.pack",
        version_name=str(d.get("version_name") or ""),
        version_code=code,
        source=str(d.get("source") or "axml"),
    )


def parse_apk_manifest(apk_path: Path) -> PackageInfo:
    try:
        from pyaxmlparser import APK  # type: ignore

        a = APK(str(apk_path))
        perms = []
        try:
            perms = list(a.get_permissions() or [])[:50]
        except Exception:
            perms = []
        code = a.version_code or 0
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = 0
        if a.package:
            return PackageInfo(
                name=a.package,
                version_name=str(a.version_name or ""),
                version_code=code,
                permissions=perms,
                source="pyaxmlparser",
            )
    except Exception:
        pass
    from gameaihack.core.axml import parse_manifest_apk

    return _pkg_from_dict(parse_manifest_apk(apk_path))


def parse_manifest_blob(data: bytes) -> PackageInfo:
    from gameaihack.core.axml import parse_manifest_bytes

    return _pkg_from_dict(parse_manifest_bytes(data))


def logical_paths(
    input_path: Path,
    extra_obbs: Iterable[Path] | None = None,
    hotupdate: Path | None = None,
) -> tuple[list[str], ContainerMeta, PackageInfo]:
    extra_obbs = [Path(p) for p in (extra_obbs or [])]
    kind = detect_kind(input_path)
    paths: set[str] = set()
    inner_apks: list[str] = []
    inner_obbs: list[str] = []
    xman = None
    files_meta = [
        {
            "kind": kind,
            "path": str(input_path),
            "bytes": input_path.stat().st_size if input_path.is_file() else 0,
        }
    ]
    pkg = PackageInfo()

    if kind == "dir":
        from gameaihack.core.fs import rel_files

        paths.update(rel_files(input_path))
        meta = ContainerMeta(kind=kind, files=files_meta)
        return sorted(paths), meta, pkg

    if kind == "apk":
        paths.update(_iter_zip_names(input_path))
        pkg = parse_apk_manifest(input_path)
        inner_apks = [input_path.name]
    elif kind in {"xapk", "apks", "zip"}:
        if not _is_zip(input_path):
            raise IngestError(f"无法打开：{input_path}")
        xman = read_xapk_manifest(input_path) if kind == "xapk" else None
        with zipfile.ZipFile(input_path) as z:
            names = z.namelist()
            inner_apks = [n for n in names if n.lower().endswith(".apk")]
            inner_obbs = [n for n in names if n.lower().endswith(".obb")]
            for n in names:
                if n.endswith("/"):
                    continue
                paths.add(n.replace("\\", "/"))
            import io

            base = pick_base_apk(inner_apks)
            for n in inner_apks:
                try:
                    raw = z.read(n)
                except KeyError:
                    continue
                try:
                    with zipfile.ZipFile(io.BytesIO(raw)) as inner:
                        for inn in inner.namelist():
                            if not inn.endswith("/"):
                                paths.add(inn.replace("\\", "/"))
                        if pkg.name == "unknown.pack" and (n == base or not base):
                            try:
                                man = inner.read("AndroidManifest.xml")
                            except KeyError:
                                man = b""
                            if man:
                                parsed = parse_manifest_blob(man)
                                if parsed.name != "unknown.pack":
                                    pkg = parsed
                except zipfile.BadZipFile:
                    continue
            for n in inner_obbs:
                try:
                    raw = z.read(n)
                except KeyError:
                    continue
                bio = io.BytesIO(raw)
                if zipfile.is_zipfile(bio):
                    bio.seek(0)
                    with zipfile.ZipFile(bio) as obb:
                        for inn in obb.namelist():
                            if not inn.endswith("/"):
                                paths.add(inn.replace("\\", "/"))
        if xman:
            name = xman.get("package_name") or xman.get("packagename")
            if name:
                pkg.name = name
                pkg.source = "xapk_manifest"
    elif kind == "obb":
        if zipfile.is_zipfile(input_path):
            paths.update(_iter_zip_names(input_path))
        else:
            paths.add(input_path.name)
    else:
        raise IngestError(f"未知容器：{kind}")

    for obb in extra_obbs:
        files_meta.append(
            {"kind": "obb", "path": str(obb), "bytes": obb.stat().st_size if obb.exists() else 0}
        )
        if obb.exists() and zipfile.is_zipfile(obb):
            paths.update(_iter_zip_names(obb))
            inner_obbs.append(str(obb))
        elif obb.exists():
            paths.add(obb.name)

    if hotupdate and hotupdate.exists():
        files_meta.append({"kind": "hotupdate", "path": str(hotupdate), "bytes": 0})
        from gameaihack.core.fs import rel_files

        paths.update(rel_files(hotupdate))

    if xman and pkg.name == "unknown.pack":
        pkg.name = xman.get("package_name") or pkg.name

    meta = ContainerMeta(
        kind=kind,
        files=files_meta,
        inner_apks=inner_apks,
        inner_obbs=inner_obbs,
        xapk_manifest=xman,
    )
    return sorted(paths), meta, pkg


def unpack_to(
    input_path: Path,
    dest: Path,
    extra_obbs: Iterable[Path] | None = None,
    hotupdate: Path | None = None,
) -> PackageInfo:
    extra_obbs = [Path(p) for p in (extra_obbs or [])]
    kind = detect_kind(input_path)
    container = dest / "container"
    apks_dir = dest / "apks"
    obb_dir = dest / "obb"
    merged = dest / "merged"
    for d in (container, apks_dir, obb_dir, merged):
        d.mkdir(parents=True, exist_ok=True)

    apk_extract_order: list[Path] = []
    pkg = PackageInfo()

    def extract_apk_file(apk_file: Path, name: str) -> None:
        out = apks_dir / name
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(apk_file) as z:
            safe_extract(z, out)
        apk_extract_order.append(out)

    if kind == "dir":
        shutil.copytree(input_path, merged, dirs_exist_ok=True)
        return pkg

    if kind == "apk":
        with zipfile.ZipFile(input_path) as z:
            safe_extract(z, container)
        extract_apk_file(input_path, input_path.stem)
        pkg = parse_apk_manifest(input_path)
    elif kind in {"xapk", "apks", "zip"}:
        with zipfile.ZipFile(input_path) as z:
            safe_extract(z, container)
        xman = read_xapk_manifest(input_path)
        apk_files = sorted(container.rglob("*.apk"), key=lambda p: p.name.lower())
        base = None
        for p in apk_files:
            if p.name.lower() in {"base.apk"} or p.stem.lower() == "base":
                base = p
                break
        ordered = []
        if base:
            ordered.append(base)
        ordered.extend([p for p in apk_files if p != base])
        for i, p in enumerate(ordered):
            extract_apk_file(p, p.stem or f"split{i}")
            if pkg.name == "unknown.pack":
                pkg = parse_apk_manifest(p)
        if xman and pkg.name == "unknown.pack":
            pkg.name = xman.get("package_name") or pkg.name
            pkg.source = "xapk_manifest"
        for obb in container.rglob("*.obb"):
            dest_obb = obb_dir / obb.name
            dest_obb.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(obb, dest_obb)
            if zipfile.is_zipfile(dest_obb):
                with zipfile.ZipFile(dest_obb) as z:
                    safe_extract(z, obb_dir / dest_obb.stem)
    else:
        raise IngestError(f"analyze 不支持：{kind}")

    for obb in extra_obbs:
        if not obb.exists():
            continue
        dest_obb = obb_dir / obb.name
        shutil.copy2(obb, dest_obb)
        if zipfile.is_zipfile(obb):
            with zipfile.ZipFile(obb) as z:
                safe_extract(z, obb_dir / obb.stem)

    def overlay(src: Path) -> None:
        if not src.exists():
            return
        from gameaihack.core.fs import iter_files, link_or_copy

        for p in iter_files(src):
            rel = p.relative_to(src)
            link_or_copy(p, merged / rel)

    for apk_root in apk_extract_order:
        overlay(apk_root)
    for child in obb_dir.iterdir() if obb_dir.exists() else []:
        if child.is_dir():
            overlay(child)
    if hotupdate and hotupdate.exists():
        overlay(hotupdate)
    return pkg


def walk_files(root: Path) -> list[str]:
    from gameaihack.core.fs import rel_files

    return rel_files(root)


def has_remote_catalog(paths: list[str], merged: Path | None = None) -> bool:
    catalogs = [p for p in paths if match_glob(p, "**/catalog.json") or p.endswith("catalog.json")]
    if not catalogs:
        return False
    if merged is None:
        return True
    for rel in catalogs:
        fp = merged / rel
        if not fp.exists():
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")[:20000].lower()
        except OSError:
            continue
        if "http://" in text or "https://" in text:
            return True
    return False
