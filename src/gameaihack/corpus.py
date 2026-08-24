"""从解包目录收集「原始文件」给 LLM / DSH 读。"""

from __future__ import annotations

from pathlib import Path

from gameaihack.layout import design_dir, extract_dir, ir_dir, unpack_dir
from gameaihack.unity_index import _ascii_strings

TEXT_EXT = {
    ".json",
    ".xml",
    ".lua",
    ".js",
    ".ts",
    ".txt",
    ".csv",
    ".plist",
    ".yml",
    ".yaml",
    ".tmx",
    ".jsonc",
    ".md",
    ".ini",
    ".cfg",
    ".manifest",
    ".prop",
}
SKIP_PARTS = {
    "applovin",
    "mbridge",
    "facebook",
    "firebase",
    "kotlin",
    "okhttp3",
    "androidx",
    "play-services",
    "google/protobuf",
    "helpshift",
    "iads",
    "ad-viewer",
    "omsdk",
    "omid",
    "fyb_",
    "ia_mraid",
    "ia_js_",
    "dll-resources",
    "/res/",
    ".html",
    "multidex",
    "google-services",
}
GAME_HINTS = (
    "chapter",
    "level",
    "catalog",
    "addressable",
    "manifest",
    "claim",
    "gamesetting",
    "boot.config",
    "aa/",
    "sling",
    "bird",
    "pig",
    "shop",
    "iap",
    "reward",
    "season",
    "clan",
    "costume",
    "bundle",
)
MAX_FILE = 80_000
MAX_FILES = 60
EXTRA_NAMES = {"boot.config", "catalog_strings.txt", "addressable_bundles.txt", "streaming_assets.txt"}


def _keep_catalog_line(s: str) -> bool:
    low = s.lower()
    keys = (
        "chapter",
        "level",
        "bird",
        "pig",
        "sling",
        "iap",
        "shop",
        "coin",
        "gem",
        "energy",
        "stamina",
        "season",
        "clan",
        "reward",
        "costume",
        "hat",
        "offer",
        "hatch",
        "saga",
        "arena",
        "tower",
        "gacha",
        "card",
        "spell",
        "heart",
        "feather",
        "eagle",
        "deck",
        "room",
    )
    return any(k in low for k in keys)


def _aa_dir(job_dir: Path) -> Path | None:
    unpacked = unpack_dir(job_dir)
    candidates = [
        unpacked / "merged" / "assets" / "aa",
        unpacked / "apks" / "UnityDataAssetPack" / "assets" / "aa",
    ]
    apks = unpacked / "apks"
    if apks.is_dir():
        for child in apks.iterdir():
            if child.is_dir():
                candidates.append(child / "assets" / "aa")
    for p in candidates:
        if (p / "catalog.bin").is_file() or p.is_dir():
            if p.is_dir():
                return p
    return None


def write_binary_extracts(job_dir: Path) -> list[Path]:
    """把 catalog.bin / bundle 文件名抽成可读文本，供模型读。"""
    dest = design_dir(job_dir) / "ai" / "_extracts"
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    merged = unpack_dir(job_dir) / "merged"
    aa = _aa_dir(job_dir)
    catalog = (aa / "catalog.bin") if aa else merged / "assets" / "aa" / "catalog.bin"
    if catalog.is_file() and catalog.stat().st_size < 20_000_000:
        lines = [s for s in _ascii_strings(catalog.read_bytes(), min_len=6) if _keep_catalog_line(s)]
        # 去重保序
        seen: set[str] = set()
        uniq: list[str] = []
        for s in lines:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
            if len(uniq) >= 400:
                break
        out = dest / "catalog_strings.txt"
        out.write_text("\n".join(uniq) + "\n", encoding="utf-8")
        written.append(out)
    android = (aa / "Android") if aa else merged / "assets" / "aa" / "Android"
    if android.is_dir():
        names = sorted(p.name for p in android.iterdir() if p.is_file())
        out = dest / "addressable_bundles.txt"
        out.write_text("\n".join(names) + "\n", encoding="utf-8")
        written.append(out)
    assets = merged / "assets"
    if assets.is_dir():
        props = sorted(p.name for p in assets.glob("*") if p.suffix.lower() in {".manifest", ".prop", ".unity3d", ".asset"} or "propbundle" in p.name.lower())
        if props:
            out = dest / "streaming_assets.txt"
            out.write_text("\n".join(props) + "\n", encoding="utf-8")
            written.append(out)
    return written


def _score(path: Path, job_dir: Path) -> int:
    try:
        rel = path.relative_to(job_dir).as_posix().lower()
    except ValueError:
        rel = path.as_posix().lower()
    name = path.name.lower()
    if any(s in rel for s in SKIP_PARTS):
        return -1
    if path.suffix.lower() == ".xml" and "/res/" in rel:
        return -1
    score = 1
    if name in {"claims.json", "levels_index.json", "tables_index.json", "fingerprint.json"}:
        score += 80
    if name == "game.ir.json":
        return -1
    hints = (
        ("catalog_strings", 70),
        ("addressable_bundles", 60),
        ("streaming_assets", 50),
        ("aa/", 40),
        ("catalog", 40),
        ("chapter", 35),
        ("level", 30),
        ("manifest", 25),
        ("addressable", 25),
        ("gamesetting", 20),
        ("boot.config", 20),
        ("scriptingassemblies", 10),
        ("assets/", 8),
        ("ir/", 15),
    )
    for kw, pts in hints:
        if kw in rel or kw in name:
            score += pts
    return score


def iter_source_files(job_dir: Path) -> list[Path]:
    write_binary_extracts(job_dir)
    roots = [
        design_dir(job_dir) / "ai" / "_extracts",
        ir_dir(job_dir),
        job_dir / "raw" / "fingerprint.json",
        job_dir / "fingerprint.json",
        extract_dir(job_dir) / "normalized" / "configs",
        extract_dir(job_dir) / "normalized" / "scripts",
        extract_dir(job_dir) / "normalized" / "maps",
        unpack_dir(job_dir) / "merged" / "assets",
    ]
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = [p for p in root.rglob("*") if p.is_file()]
        else:
            continue
        for p in candidates:
            if p.suffix.lower() not in TEXT_EXT and p.name not in EXTRA_NAMES:
                continue
            rel = p.as_posix().lower()
            if any(s in rel for s in SKIP_PARTS):
                continue
            try:
                if p.stat().st_size < 2 or p.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            key = p.resolve().as_posix()
            if key in seen:
                continue
            seen.add(key)
            found.append(p)
    ranked = [p for p in found if _score(p, job_dir) > 0]
    ranked.sort(key=lambda p: (-_score(p, job_dir), p.as_posix()))
    uniq: list[Path] = []
    seen_names: set[tuple[str, int]] = set()
    for p in ranked:
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        key = (p.name.lower(), sz)
        if key in seen_names:
            continue
        seen_names.add(key)
        uniq.append(p)
        if len(uniq) >= MAX_FILES:
            break
    return uniq


def index_markdown(job_dir: Path, files: list[Path]) -> str:
    lines = ["# 原始文件索引\n", "DSH / LLM 应读这些，而不是 apk / so。\n", "| 路径 | 字节 |", "|---|---|"]
    for p in files:
        try:
            rel = p.relative_to(job_dir).as_posix()
        except ValueError:
            rel = str(p)
        try:
            n = p.stat().st_size
        except OSError:
            n = 0
        lines.append(f"| `{rel}` | {n} |")
    return "\n".join(lines) + "\n"


def batch_text(job_dir: Path, files: list[Path], *, budget: int = 48_000) -> list[str]:
    batches: list[str] = []
    buf: list[str] = []
    used = 0
    for p in files:
        try:
            rel = p.relative_to(job_dir).as_posix()
        except ValueError:
            rel = str(p)
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[:MAX_FILE]
        except OSError:
            continue
        if not text.strip():
            continue
        chunk = f"\n\n===== FILE {rel} =====\n{text}"
        if used + len(chunk) > budget and buf:
            batches.append("".join(buf))
            buf, used = [], 0
        buf.append(chunk)
        used += len(chunk)
    if buf:
        batches.append("".join(buf))
    return batches
