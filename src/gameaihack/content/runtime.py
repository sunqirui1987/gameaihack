from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from gameaihack.core.fs import so_files
from gameaihack.extract.stringsutil import nearby_keys, strings_from_file


def run_runtime(
    merged: Path,
    dest: Path,
    *,
    device: str | None,
    package: str | None,
    mode: str,
) -> dict:
    """深挖：静态扫 so 字符串；若给了设备，仅 adb pull 已安装包的 files 缓存。

    不注入、不改内存、不 hook 支付。
    """
    info: dict = {"so_strings": 0, "pulled": False, "warnings": []}
    dest.mkdir(parents=True, exist_ok=True)
    all_strings: list[str] = []
    for so in so_files(merged):
        all_strings.extend(strings_from_file(so)[:2000])
    uniq = []
    seen = set()
    for s in all_strings:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    info["so_strings"] = len(uniq)
    (dest / "so_strings.txt").write_text("\n".join(uniq[:8000]), encoding="utf-8")
    info["xxtea_candidates"] = nearby_keys(uniq)
    info["key_found"] = bool(info["xxtea_candidates"])

    if mode != "deep" or not device:
        if mode == "deep" and not device:
            info["warnings"].append("deep_without_device")
        return info

    if not shutil.which("adb"):
        info["warnings"].append("adb_missing")
        return info
    if not package or package == "unknown.pack":
        info["warnings"].append("package_unknown_skip_pull")
        return info
    remote = f"/sdcard/Android/data/{package}/files"
    pull_dir = dest / "device_files"
    pull_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["adb", "-s", device, "pull", remote, str(pull_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        info["pulled"] = proc.returncode == 0
        info["adb_out"] = (proc.stdout or "")[-500:]
        if proc.returncode != 0:
            info["warnings"].append("adb_pull_failed")
    except (OSError, subprocess.TimeoutExpired) as e:
        info["warnings"].append(f"adb:{e}")
    return info
