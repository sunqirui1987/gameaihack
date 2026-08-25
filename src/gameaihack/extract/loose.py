from __future__ import annotations

from pathlib import Path

from gameaihack.core.fs import iter_files, link_or_copy, sha256_path
from gameaihack.extract.base import (
    KIND_DIR,
    ExtractItem,
    ExtractReport,
    kind_from_suffix,
)
from gameaihack.extract.magic import shannon_entropy, sniff, suffix_for_kind

SKIP_PARTS = {
    "meta-inf",
    "kotlin",
    "kotlinx",
    "okhttp3",
    "okio",
    "androidx",
    "com/google",
    "com/android",
    "res/color",
}
SKIP_SUFFIX = {
    ".so",
    ".dex",
    ".arsc",
    ".apk",
    ".jar",
    ".class",
    ".kotlin_module",
    ".version",
    ".mf",
    ".sf",
    ".rsa",
    ".dsa",
    ".exe",
}
SKIP_NAMES = {"androidmanifest.xml", "resources.arsc", "debug.keystore"}
SKIP_DIRS = {
    "meta-inf",
    "kotlin",
    "kotlinx",
    "okhttp3",
    "okio",
    "androidx",
}


def extract_loose(merged: Path, dest: Path, *, max_files: int = 2500) -> ExtractReport:
    report = ExtractReport(adapter="loose")
    if not merged.exists():
        report.warnings.append("merged_missing")
        return report
    dest.mkdir(parents=True, exist_ok=True)
    for path in iter_files(merged, skip_dirs=SKIP_DIRS):
        rel = path.relative_to(merged).as_posix()
        low = rel.lower()
        report.discovered += 1
        if any(p in low for p in SKIP_PARTS):
            continue
        if Path(low).name in SKIP_NAMES:
            continue
        suf = path.suffix.lower()
        if suf in SKIP_SUFFIX:
            continue
        kind = kind_from_suffix(rel)
        head = b""
        if kind is None:
            try:
                with path.open("rb") as f:
                    head = f.read(4096)
            except OSError:
                continue
            kind = sniff(head)
        if kind is None:
            if suf in {".json", ".csv", ".xml", ".txt", ".lua", ".js"}:
                kind = "config"
            else:
                if not head:
                    try:
                        with path.open("rb") as f:
                            head = f.read(4096)
                    except OSError:
                        continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if shannon_entropy(head) >= 7.2 and size > 64:
                    report.encrypted += 1
                    continue
                continue
        if len(report.items) >= max_files:
            report.warnings.append("export_capped")
            break
        folder = KIND_DIR.get(kind, "misc")
        rel_out = rel.replace("..", "_")
        if not Path(rel_out).suffix:
            rel_out = rel_out + suffix_for_kind(kind, head)
        target = dest / folder / rel_out
        try:
            link_or_copy(path, target)
        except OSError as e:
            report.warnings.append(f"copy_fail:{rel}:{e}")
            continue
        try:
            size = target.stat().st_size
        except OSError:
            continue
        report.items.append(
            ExtractItem(
                kind=kind,
                name=path.stem,
                original_path=rel,
                export_rel=target.relative_to(dest).as_posix(),
                sha256=sha256_path(target),
                bytes=size,
                extractor="loose",
                meta={"suffix": suf},
            )
        )
    return report
