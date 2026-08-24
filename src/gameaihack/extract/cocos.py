from __future__ import annotations

import gzip
import shutil
import subprocess
from pathlib import Path

from gameaihack.extract.base import KIND_DIR, ExtractItem, ExtractReport, sha256_path
from gameaihack.extract.stringsutil import nearby_keys, strings_from_file
from gameaihack.extract.xxtea import looks_text, strip_sign, xxtea_decrypt


def extract_cocos(merged: Path, dest: Path) -> ExtractReport:
    report = ExtractReport(adapter="cocos")
    dest.mkdir(parents=True, exist_ok=True)
    keys = _collect_keys(merged)
    report.extra["xxtea_key_candidates"] = len(keys)
    report.extra["xxtea_key_found"] = False

    patterns = ("*.lua", "*.luac", "*.luax", "*.js", "*.jsc", "*.jsc.bin")
    files: list[Path] = []
    for pat in patterns:
        files.extend(merged.rglob(pat))
    report.discovered = len(files)

    for path in files:
        rel = path.relative_to(merged).as_posix()
        data = path.read_bytes()
        text: bytes | None = None
        if looks_text(data):
            text = data
        elif data.startswith(b"\x1bLua"):
            text = _unluac(path)
            if text is None:
                report.warnings.append(f"lua_bytecode:{rel}")
                continue
        else:
            report.encrypted += 1
            body, sign = strip_sign(data)
            for key in keys:
                plain = xxtea_decrypt(body, key.encode("utf-8"))
                if not plain:
                    continue
                if plain.startswith(b"\x1f\x8b"):
                    try:
                        plain = gzip.decompress(plain)
                    except OSError:
                        continue
                if looks_text(plain) or plain[:4] in (b"\x1bLua", b"LuaQ"):
                    text = plain
                    report.extra["xxtea_key_found"] = True
                    report.extra["xxtea_sign"] = sign
                    break
        if text is None:
            report.warnings.append(f"encrypted_script:{rel}")
            continue
        folder = KIND_DIR["script"]
        out_name = path.name
        if out_name.endswith(".jsc"):
            out_name = out_name[:-4] + ".js"
        if out_name.endswith(".luac") or out_name.endswith(".luax"):
            out_name = Path(out_name).stem + ".lua"
        target = dest / folder / rel
        if target.suffix in {".jsc", ".luac", ".luax"}:
            target = target.with_suffix(".js" if "js" in path.suffix else ".lua")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text)
        report.items.append(
            ExtractItem(
                kind="script",
                name=path.stem,
                original_path=rel,
                export_rel=target.relative_to(dest).as_posix(),
                sha256=sha256_path(target),
                bytes=target.stat().st_size,
                extractor="cocos",
                meta={"decrypted": not looks_text(data)},
            )
        )
    return report


def _collect_keys(merged: Path) -> list[str]:
    keys: list[str] = []
    for so in merged.rglob("*.so"):
        strs = strings_from_file(so, min_len=4)
        for k in nearby_keys(strs):
            if k not in keys:
                keys.append(k)
    return keys


def _unluac(path: Path) -> bytes | None:
    exe = shutil.which("unluac") or shutil.which("unluac.jar")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            ["java", "-jar", exe, str(path)] if exe.endswith(".jar") else [exe, str(path)],
            capture_output=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None
