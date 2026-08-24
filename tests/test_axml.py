from gameaihack.axml import parse_manifest_bytes


def test_text_manifest_package():
    xml = b"""<?xml version="1.0"?><manifest package="com.example.puzzle" android:versionName="1.2" android:versionCode="3"></manifest>"""
    info = parse_manifest_bytes(xml)
    assert info["name"] == "com.example.puzzle"
    assert info["version_name"] == "1.2"
    assert info["version_code"] == 3
