import io
import json
import urllib.error
import zipfile
from pathlib import Path

from gameaihack.ingest.fetch import (
    FetchError,
    fetch_package,
    find_cached,
    looks_like_package,
    normalize_package,
    resolve_proxy,
)
from tests.helpers import unity_apk_files, write_zip


def test_resolve_proxy_cli_env_yaml(monkeypatch):
    for k in (
        "GAMEAIHACK_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
        "http_proxy",
        "HTTP_PROXY",
        "ALL_PROXY",
        "all_proxy",
    ):
        monkeypatch.delenv(k, raising=False)
    yaml_proxy = resolve_proxy()
    assert yaml_proxy == "http://127.0.0.1:9090" or yaml_proxy is None or yaml_proxy.startswith("http")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9090")
    assert resolve_proxy() == "http://127.0.0.1:9090"
    monkeypatch.setenv("GAMEAIHACK_PROXY", "http://127.0.0.1:8888")
    assert resolve_proxy() == "http://127.0.0.1:8888"
    assert resolve_proxy("http://10.0.0.1:1080") == "http://10.0.0.1:1080"
    assert resolve_proxy(disable=True) is None


def test_normalize_play_url():
    assert (
        normalize_package("https://play.google.com/store/apps/details?id=com.unciv.app")
        == "com.unciv.app"
    )
    assert normalize_package("com.example.game") == "com.example.game"
    assert looks_like_package("com.unciv.app")
    assert not looks_like_package("not-a-path-or-pkg")
    assert not looks_like_package("missing.apk")


def test_fetch_fdroid_mocked(monkeypatch, tmp_path: Path):
    apk_bytes = io.BytesIO()
    with zipfile.ZipFile(apk_bytes, "w") as zf:
        for name, data in unity_apk_files().items():
            zf.writestr(name, data)
    blob = apk_bytes.getvalue()

    class Resp:
        def __init__(self, body: bytes, ctype: str):
            self._body = body
            self.headers = {"Content-Type": ctype}

        def read(self, n: int = -1):
            if n is None or n < 0:
                data, self._body = self._body, b""
                return data
            chunk, self._body = self._body[:n], self._body[n:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    def fake_urlopen(req, timeout=0):
        url = getattr(req, "full_url", req)
        if "/api/v1/packages/" in url:
            return Resp(
                json.dumps({"packageName": "com.example.puzzle", "suggestedVersionCode": 9}).encode(),
                "application/json",
            )
        if url.endswith(".apk"):
            return Resp(blob, "application/vnd.android.package-archive")
        raise urllib.error.URLError("no")

    monkeypatch.setattr("gameaihack.ingest.fetch.urllib.request.urlopen", fake_urlopen)
    result = fetch_package("com.example.puzzle", tmp_path, source="fdroid", no_proxy=True)
    assert result.source == "fdroid"
    assert result.path.exists()
    assert zipfile.is_zipfile(result.path)


def test_find_cached_prefers_xapk_and_skips_part(tmp_path: Path):
    pkg = "com.example.puzzle"
    write_zip(tmp_path / f"{pkg}.xapk", unity_apk_files())
    (tmp_path / f"{pkg}.apk.part").write_bytes(b"PK" + b"\x00" * 400)
    (tmp_path / f"{pkg}.apk").write_bytes(b"not-a-zip" * 40)
    hit = find_cached(pkg, tmp_path)
    assert hit == tmp_path / f"{pkg}.xapk"


def test_fetch_uses_cache_without_network(monkeypatch, tmp_path: Path):
    pkg = "com.example.puzzle"
    write_zip(tmp_path / f"{pkg}.xapk", unity_apk_files())

    def boom(*_a, **_k):
        raise AssertionError("cache hit must not touch network")

    monkeypatch.setattr("gameaihack.ingest.fetch.urllib.request.urlopen", boom)
    result = fetch_package(pkg, tmp_path, source="fdroid", no_proxy=True)
    assert result.source == "cache"
    assert result.path == tmp_path / f"{pkg}.xapk"


def test_force_fetch_skips_cache(monkeypatch, tmp_path: Path):
    pkg = "com.example.puzzle"
    write_zip(tmp_path / f"{pkg}.xapk", unity_apk_files())
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        raise urllib.error.URLError("forced")

    monkeypatch.setattr("gameaihack.ingest.fetch.urllib.request.urlopen", fake_urlopen)
    try:
        fetch_package(pkg, tmp_path, source="fdroid", no_proxy=True, force=True)
    except FetchError:
        pass
    else:
        raise AssertionError("force-fetch should try network")
    assert calls["n"] >= 1


def test_empty_pkg_dir_is_not_cache(tmp_path: Path):
    pkg = "com.example.puzzle"
    (tmp_path / pkg).mkdir()
    assert find_cached(pkg, tmp_path) is None


def test_fetch_unknown_source():
    try:
        fetch_package("com.foo.bar", Path("/tmp"), source="nope", no_proxy=True)
    except FetchError as e:
        assert "未知来源" in str(e)
    else:
        raise AssertionError("expected FetchError")
