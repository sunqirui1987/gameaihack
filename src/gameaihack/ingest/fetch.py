from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_RE = re.compile(r"^[A-Za-z][\w]*(\.[A-Za-z][\w]*)+$")
PLAY_URL_RE = re.compile(r"(?:id=|/store/apps/details\?id=)([A-Za-z][\w]*(?:\.[A-Za-z][\w]*)+)")
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class FetchError(Exception):
    pass


@dataclass
class FetchResult:
    package: str
    source: str
    path: Path
    extra_obbs: list[Path] = field(default_factory=list)
    note: str = ""


def looks_like_package(s: str) -> bool:
    s = s.strip()
    if PLAY_URL_RE.search(s):
        return True
    p = Path(s)
    if p.exists() or p.suffix.lower() in {".apk", ".xapk", ".apks", ".obb", ".zip"}:
        return False
    return bool(PACKAGE_RE.match(s))


def normalize_package(s: str) -> str:
    s = s.strip()
    m = PLAY_URL_RE.search(s)
    if m:
        return m.group(1)
    if PACKAGE_RE.match(s):
        return s
    raise FetchError(f"不是包名或 Play 链接：{s}")


def resolve_proxy(explicit: str | None = None, *, disable: bool = False) -> str | None:
    """下载代理：--proxy > 环境变量 > configs/pipeline.yaml fetch.proxy > 直连。"""
    if disable:
        return None
    if explicit:
        return explicit.strip() or None
    for key in (
        "GAMEAIHACK_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
        "http_proxy",
        "HTTP_PROXY",
        "ALL_PROXY",
        "all_proxy",
    ):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return _proxy_from_yaml()


def _proxy_from_yaml() -> str | None:
    try:
        from gameaihack.core.paths import load_yaml

        data = load_yaml("pipeline.yaml") or {}
        val = (data.get("fetch") or {}).get("proxy")
        if val in (None, "", False):
            return None
        return str(val).strip() or None
    except Exception:
        return None


MIN_CACHE_BYTES = 256
_CACHE_PREF = {".xapk": 3, ".apks": 2, ".apk": 1}


def human_size(path: Path) -> str:
    if path.is_dir():
        n = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    else:
        n = path.stat().st_size
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.0f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def _valid_cached_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name.endswith(".part"):
        return False
    try:
        if path.stat().st_size < MIN_CACHE_BYTES:
            return False
    except OSError:
        return False
    return zipfile.is_zipfile(path)


def find_cached(pkg: str, dest_dir: Path) -> Path | None:
    """本地已有完整包则返回路径。忽略 .part 和坏 zip。优先最近写入的文件。"""
    dest_dir = Path(dest_dir)
    if not dest_dir.is_dir():
        return None
    files: list[Path] = []
    for p in (
        dest_dir / f"{pkg}.xapk",
        dest_dir / f"{pkg}.apks",
        dest_dir / f"{pkg}.apk",
    ):
        if _valid_cached_file(p):
            files.append(p)
    for p in dest_dir.glob(f"{pkg}_*.apk"):
        if _valid_cached_file(p):
            files.append(p)
    if files:
        return max(
            files,
            key=lambda p: (p.stat().st_mtime, _CACHE_PREF.get(p.suffix.lower(), 0), p.stat().st_size),
        )
    folder = dest_dir / pkg
    if folder.is_dir():
        apks = [p for p in folder.glob("*.apk") if _valid_cached_file(p)]
        if len(apks) > 1:
            return folder
        if len(apks) == 1:
            return apks[0]
    return None


def _cleanup_part_files(pkg: str, dest_dir: Path) -> None:
    for p in dest_dir.glob(f"{pkg}*.part"):
        try:
            p.unlink()
        except OSError:
            pass


def fetch_package(
    package: str,
    dest_dir: Path,
    *,
    source: str = "auto",
    timeout: int = 120,
    proxy: str | None = None,
    no_proxy: bool = False,
    force: bool = False,
) -> FetchResult:
    pkg = normalize_package(package)
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    from gameaihack.core.progress import log

    if not force:
        cached = find_cached(pkg, dest_dir)
        if cached:
            log(f"[cache] 已有 {cached.name}（{human_size(cached)}），跳过下载")
            _cleanup_part_files(pkg, dest_dir)
            return FetchResult(package=pkg, source="cache", path=cached, note="local cache")

    px = resolve_proxy(proxy, disable=no_proxy)
    sources = _order(source)
    errors: list[str] = []
    n = len(sources)
    for i, src in enumerate(sources, 1):
        log(f"[{i}/{n}] 尝试 {src} …")
        try:
            if src == "fdroid":
                result = _fetch_fdroid(pkg, dest_dir, timeout=timeout, proxy=px)
            elif src == "apkpure":
                result = _fetch_apkpure(pkg, dest_dir, timeout=timeout, proxy=px)
            elif src == "gplaydl":
                result = _fetch_gplaydl(pkg, dest_dir, proxy=px)
            else:
                result = _fetch_evozi(pkg, dest_dir, timeout=timeout, proxy=px)
            log(f"[{i}/{n}] {src} 完成 → {result.path.name}")
            _cleanup_part_files(pkg, dest_dir)
            return result
        except FetchError as e:
            short = str(e).split("\n")[0][:120]
            log(f"[{i}/{n}] {src} 跳过：{short}")
            errors.append(f"{src}: {e}")
            continue
    hint = (
        f"浏览器打开 https://apps.evozi.com/apk-downloader/ 粘贴 {pkg}\n"
        "或 gplaydl link 后用 --source gplaydl"
    )
    raise FetchError("下载失败：\n- " + "\n- ".join(errors) + "\n" + hint)


def _order(source: str) -> list[str]:
    if source == "auto":
        return ["fdroid", "apkpure", "gplaydl", "evozi"]
    if source in {"fdroid", "apkpure", "gplaydl", "evozi"}:
        return [source]
    raise FetchError(f"未知来源 {source}（fdroid|apkpure|gplaydl|evozi|auto）")


def _urlopen(url: str, timeout: int = 60, proxy: str | None = None):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def _fetch_fdroid(pkg: str, dest_dir: Path, timeout: int, proxy: str | None = None) -> FetchResult:
    api = f"https://f-droid.org/api/v1/packages/{pkg}"
    try:
        with _urlopen(api, timeout=min(timeout, 30), proxy=proxy) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FetchError("F-Droid 没有这个包") from e
        raise FetchError(f"F-Droid API {e.code}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise FetchError(f"F-Droid 不可达：{e}") from e
    vc = meta.get("suggestedVersionCode")
    if not vc:
        raise FetchError("F-Droid 无 suggestedVersionCode")
    apk_name = f"{pkg}_{vc}.apk"
    mirrors = [
        f"https://f-droid.org/repo/{apk_name}",
        f"https://ftp.fau.de/fdroid/repo/{apk_name}",
        f"https://mirror.eu.ossplanet.net/fdroid/repo/{apk_name}",
    ]
    out = dest_dir / f"{pkg}.apk"
    last = None
    for url in mirrors:
        try:
            _download(url, out, timeout=timeout, proxy=proxy, label="F-Droid")
            if zipfile.is_zipfile(out):
                return FetchResult(package=pkg, source="fdroid", path=out, note=f"versionCode={vc}")
        except FetchError as e:
            last = e
            continue
    raise FetchError(str(last) if last else "F-Droid 镜像均失败")


def _fetch_gplaydl(pkg: str, dest_dir: Path, proxy: str | None = None) -> FetchResult:
    exe = shutil.which("gplaydl")
    if not exe:
        raise FetchError("未安装 gplaydl")
    linked = (Path.home() / ".config/gplaydl/config.json").exists() or os.environ.get("GPLAYDL_API_KEY")
    if not linked:
        raise FetchError("gplaydl 未 link（跳过）。需要时：gplaydl link")
    outdir = dest_dir / pkg
    outdir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if proxy:
        env["https_proxy"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["HTTP_PROXY"] = proxy
        env["ALL_PROXY"] = proxy
    from gameaihack.core.progress import log

    log("  gplaydl 正在下载（请稍候）…")
    proc = subprocess.run(
        [exe, "download", pkg, "-o", str(outdir)],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise FetchError(err or f"gplaydl exit {proc.returncode}")
    apks = sorted(outdir.glob("*.apk"))
    obbs = sorted(outdir.glob("*.obb"))
    if not apks:
        raise FetchError("gplaydl 未产出 apk")
    base = next((p for p in apks if "config." not in p.name and "split" not in p.name), apks[0])
    # 多分包时把目录交给 ingest（kind=dir）
    path = outdir if len(apks) > 1 else base
    return FetchResult(
        package=pkg,
        source="gplaydl",
        path=path,
        extra_obbs=obbs,
        note=f"apks={len(apks)} obb={len(obbs)}",
    )


def _fetch_apkpure(pkg: str, dest_dir: Path, timeout: int, proxy: str | None = None) -> FetchResult:
    """第三方镜像（APKPure CDN）。Play 免费应用常用，不需要 Google 账号。"""
    q = urllib.parse.quote(pkg)
    out = dest_dir / f"{pkg}.apk"
    urls = [
        f"https://d.apkpure.com/b/XAPK/{pkg}?version=latest",
        f"https://d.apkpure.com/b/APK/{pkg}?version=latest",
        f"https://apkpure.com/{q}/{pkg}/download?from=details",
    ]
    last: FetchError | None = None
    for url in urls:
        try:
            _download(url, out, timeout=max(timeout, 180), proxy=proxy, label="APKPure")
            if zipfile.is_zipfile(out):
                kind = "xapk" if out.suffix.lower() != ".apk" or _looks_xapk(out) else "apk"
                if kind == "xapk" and not out.name.endswith(".xapk"):
                    xapk = dest_dir / f"{pkg}.xapk"
                    out.replace(xapk)
                    out = xapk
                return FetchResult(package=pkg, source="apkpure", path=out, note=url.split("?")[0])
        except FetchError as e:
            last = e
            continue
    html_url = f"https://apkpure.com/search?q={q}"
    try:
        dl = _apkpure_from_search(pkg, timeout=timeout, proxy=proxy)
        if dl:
            _download(dl, out, timeout=max(timeout, 180), proxy=proxy, label="APKPure")
            if zipfile.is_zipfile(out):
                return FetchResult(package=pkg, source="apkpure", path=out, note=dl[:80])
    except FetchError as e:
        last = e
    raise FetchError(str(last) if last else f"APKPure 未找到 {pkg}（可打开 {html_url}）")


def _looks_xapk(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        return any(n.lower().endswith(".apk") for n in names) and "AndroidManifest.xml" not in names
    except zipfile.BadZipFile:
        return False


def _apkpure_from_search(pkg: str, timeout: int, proxy: str | None) -> str | None:
    url = f"https://apkpure.com/search?q={urllib.parse.quote(pkg)}"
    try:
        with _urlopen(url, timeout=min(timeout, 30), proxy=proxy) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError, urllib.error.HTTPError):
        return None
    # /app-slug/com.foo.bar
    m = re.search(rf'href="(https://apkpure\.com/[^"]+/{re.escape(pkg)})"', html)
    if not m:
        m = re.search(rf'href="(/[^"]+/{re.escape(pkg)})"', html)
    if not m:
        return None
    page = m.group(1)
    if page.startswith("/"):
        page = "https://apkpure.com" + page
    dl_page = page.rstrip("/") + "/download"
    try:
        with _urlopen(dl_page, timeout=min(timeout, 30), proxy=proxy) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError, urllib.error.HTTPError):
        return None
    for pat in (
        r'href="(https://download\.apkpure\.com/[^"]+)"',
        r'href="(https://d\.apkpure\.com/[^"]+)"',
        r'data-url="(https://[^"]+apkpure[^"]+)"',
    ):
        mm = re.search(pat, html)
        if mm:
            return mm.group(1).replace("&amp;", "&")
    return None


def _fetch_evozi(pkg: str, dest_dir: Path, timeout: int, proxy: str | None = None) -> FetchResult:
    """Evozi 转 apkcube；再试 APKPure CDN。"""
    out = dest_dir / f"{pkg}.apk"
    last: FetchError | None = None
    for url in (
        f"https://d.apkpure.com/b/XAPK/{pkg}?version=latest",
        f"https://d.apkpure.com/b/APK/{pkg}?version=latest",
        f"https://apkcube.com/apk/{urllib.parse.quote(pkg)}",
    ):
        try:
            _download(url, out, timeout=max(timeout, 180), proxy=proxy, label="Evozi")
            if zipfile.is_zipfile(out):
                if _looks_xapk(out):
                    xapk = dest_dir / f"{pkg}.xapk"
                    out.replace(xapk)
                    out = xapk
                return FetchResult(package=pkg, source="evozi", path=out, note=url.split("?")[0])
        except FetchError as e:
            last = e
            continue
    page = "https://apps.evozi.com/apk-downloader/"
    raise FetchError(
        f"{last or '无直链'}。可打开 {page} 粘贴 {pkg}，或先 gplaydl link"
    )


def _download(url: str, dest: Path, timeout: int, proxy: str | None = None, label: str = "下载") -> None:
    from gameaihack.core.progress import bar, bar_done

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    t0 = time.time()
    try:
        with _urlopen(url, timeout=timeout, proxy=proxy) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            total = 0
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except ValueError:
                total = 0
            head = resp.read(16)
            if head[:2] != b"PK" and ("text/html" in ctype or head.lstrip()[:1] in (b"<", b"{")):
                raise FetchError(f"得到网页而不是 apk：{url}")
            got = len(head)
            with tmp.open("wb") as f:
                f.write(head)
                bar(got, total or None, prefix=label, t0=t0)
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    bar(got, total or None, prefix=label, t0=t0)
            bar_done()
        tmp.replace(dest)
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"HTTP {e.code} {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"{url}: {e}") from e
