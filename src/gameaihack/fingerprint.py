from __future__ import annotations

from dataclasses import asdict, dataclass, field

from gameaihack.globmatch import match_glob
from gameaihack.paths import load_yaml


@dataclass
class Signal:
    path: str
    rule: str


@dataclass
class Fingerprint:
    engine: str = "unknown"
    engine_version: str | None = None
    script_backend: str | None = None
    hotupdate: list[str] = field(default_factory=list)
    protection: list[str] = field(default_factory=list)
    splits: list[str] = field(default_factory=list)
    has_obb: bool = False
    signals: list[dict] = field(default_factory=list)
    confidence: float = 0.2
    matched_rules: list[str] = field(default_factory=list)
    shell_likely: bool = False
    remote_catalog: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _load_rules() -> tuple[dict[str, int], list[dict]]:
    data = load_yaml("fingerprint_rules.yaml")
    prio = {str(k): int(v) for k, v in (data.get("priority") or {}).items()}
    return prio, list(data.get("rules") or [])


def _rule_hits(rule: dict, paths: list[str]) -> list[str]:
    patterns = rule.get("patterns") or []
    match = rule.get("match") or "glob_any"
    hits = []
    for pat in patterns:
        found = [p for p in paths if match_glob(p, pat)]
        if found:
            hits.append(found[0])
            if match == "glob_any":
                return hits
    if match == "glob_all":
        if len(hits) == len(patterns):
            return hits
        return []
    return hits


def scan_paths(
    paths: list[str],
    *,
    splits: list[str] | None = None,
    has_obb: bool = False,
    input_bytes: int = 0,
    remote_catalog: bool = False,
) -> Fingerprint:
    prio, rules = _load_rules()
    engine_hits: list[tuple[int, str, str | None]] = []
    backends: list[str] = []
    tags: list[str] = []
    matched: list[str] = []
    signals: list[dict] = []

    for rule in rules:
        hits = _rule_hits(rule, paths)
        if not hits:
            continue
        rid = rule["id"]
        matched.append(rid)
        signals.append({"path": hits[0], "rule": rid})
        if rule.get("engine"):
            eng = rule["engine"]
            engine_hits.append((prio.get(eng, 0), eng, rule.get("script_backend")))
        if rule.get("script_backend"):
            backends.append(rule["script_backend"])
        for t in rule.get("tags") or []:
            tags.append(t)

    engine = "unknown"
    script_backend = None
    if engine_hits:
        engine_hits.sort(key=lambda x: x[0], reverse=True)
        engine = engine_hits[0][1]
        script_backend = engine_hits[0][2]
        for _, eng, sb in engine_hits:
            if eng == engine and sb:
                script_backend = sb
                break
        if engine == "unity":
            if "il2cpp" in backends:
                script_backend = "il2cpp"
            elif "mono" in backends:
                script_backend = "mono"

    hotupdate = sorted({t.split(".", 1)[1] for t in tags if t.startswith("hotupdate.")})
    protection = sorted({t.split(".", 1)[1] for t in tags if t.startswith("protection.")})

    unity_has_data = any(
        match_glob(p, "assets/bin/Data/data.unity3d")
        or match_glob(p, "assets/bin/Data/*.assets")
        or match_glob(p, "assets/bin/Data/*.resource")
        or match_glob(p, "assets/bin/Data/*.resS")
        for p in paths
    )
    unreal_has_pak = any(
        p.lower().endswith(".pak") or p.lower().endswith(".ucas") for p in paths
    )

    shell_likely = False
    if engine == "unity" and not unity_has_data:
        shell_likely = True
    if engine == "unreal" and not unreal_has_pak:
        shell_likely = True
    # 体积过小单独记 tiny_package，不把「完整但很小的 2D 包」误判成壳。

    if engine in {"unity", "cocos", "unreal"} and (
        "unity_il2cpp" in matched or "unity_data" in matched or "cocos_js" in matched or "cocos_lua" in matched or "unreal" in matched
    ):
        confidence = 0.97
    elif engine != "unknown":
        confidence = 0.7
    else:
        confidence = 0.2

    return Fingerprint(
        engine=engine,
        script_backend=script_backend,
        hotupdate=hotupdate,
        protection=protection,
        splits=splits or [],
        has_obb=has_obb,
        signals=signals,
        confidence=confidence,
        matched_rules=matched,
        shell_likely=shell_likely,
        remote_catalog=remote_catalog,
    )


def scan_merged(merged: Path, **kwargs) -> Fingerprint:
    from gameaihack.ingest import walk_files

    return scan_paths(walk_files(merged), **kwargs)
