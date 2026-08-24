from gameaihack.fingerprint import scan_paths
from gameaihack.inspect_cmd import inspect_input


def test_unity_il2cpp_with_data(unity_apk):
    r = inspect_input(unity_apk)
    assert r.fingerprint["engine"] == "unity"
    assert r.fingerprint["script_backend"] == "il2cpp"
    assert "unity_il2cpp" in r.fingerprint["matched_rules"]
    assert r.fingerprint["shell_likely"] is False
    assert r.input_profile["score"] >= 60
    assert "tiny_package" not in r.input_profile["warnings"]
    assert r.package.get("name") == "com.example.puzzle"


def test_shell_apk_low_score(shell_apk):
    r = inspect_input(shell_apk)
    assert r.fingerprint["engine"] == "unity"
    assert r.fingerprint["shell_likely"] is True
    assert r.input_profile["score"] < 60
    assert "likely_shell_missing_obb" in r.input_profile["warnings"]


def test_cocos_lua_rule():
    fp = scan_paths(["lib/arm64-v8a/libcocos2dlua.so", "src/app.luac"])
    assert fp.engine == "cocos"
    assert fp.script_backend == "lua"
