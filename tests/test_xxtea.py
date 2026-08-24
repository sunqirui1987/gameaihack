from gameaihack.extract.xxtea import looks_text, xxtea_decrypt, xxtea_encrypt


def test_xxtea_roundtrip():
    raw = b"local foo = 1\nprint('hi')\n"
    key = b"1234567890abcdef"
    enc = xxtea_encrypt(raw, key)
    assert enc != raw
    out = xxtea_decrypt(enc, key)
    assert out == raw
    assert looks_text(raw)
