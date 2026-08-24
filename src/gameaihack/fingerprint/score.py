from __future__ import annotations

from gameaihack.fingerprint.scan import Fingerprint
from gameaihack.core.globmatch import match_glob


def unity_data_present(paths: list[str]) -> bool:
    return any(p.replace("\\", "/").startswith("assets/bin/Data/") for p in paths)


def unity_main_assets_present(paths: list[str]) -> bool:
    return any(
        match_glob(p, "assets/bin/Data/data.unity3d")
        or match_glob(p, "assets/bin/Data/*.assets")
        or match_glob(p, "assets/bin/Data/*.resource")
        or match_glob(p, "assets/bin/Data/*.resS")
        for p in paths
    )


def input_score(
    fp: Fingerprint,
    *,
    input_bytes: int,
    has_obb: bool,
    has_hotupdate: bool,
    unity_data_present_flag: bool,
) -> tuple[int, list[str]]:
    score = 100
    warnings: list[str] = []

    if fp.shell_likely:
        score -= 40
        warnings.append("likely_shell_missing_obb")
    if fp.engine == "unity" and not unity_data_present_flag:
        score -= 30
        warnings.append("unity_data_missing")
    if fp.remote_catalog:
        score -= 20
        warnings.append("addressables_remote")
    if fp.protection:
        score -= 5
        warnings.append("packed")
    if (
        input_bytes
        and input_bytes < 40 * 1024 * 1024
        and fp.engine in {"unity", "unreal"}
        and (fp.shell_likely or not unity_data_present_flag)
    ):
        score -= 15
        warnings.append("tiny_package")
    if has_obb:
        score += 25
    if has_hotupdate:
        score += 20
    score = max(0, min(100, score))
    seen: set[str] = set()
    out: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return score, out
