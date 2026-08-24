from __future__ import annotations

DELTA = 0x9E3779B9


def _to_ints(data: bytes, with_length: bool) -> list[int]:
    n = (len(data) + 3) // 4
    buf = data + b"\x00" * (n * 4 - len(data))
    out = [int.from_bytes(buf[i * 4 : i * 4 + 4], "little") for i in range(n)]
    if with_length:
        out.append(len(data))
    return out


def _to_bytes(ints: list[int], with_length: bool) -> bytes:
    if with_length:
        length = ints[-1]
        ints = ints[:-1]
        raw = b"".join(i.to_bytes(4, "little") for i in ints)
        return raw[:length]
    return b"".join(i.to_bytes(4, "little") for i in ints)


def _mx(z: int, y: int, s: int, k: list[int], p: int, e: int) -> int:
    return (
        (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4)))
        ^ ((s ^ y) + (k[(p & 3) ^ e] ^ z))
    ) & 0xFFFFFFFF


def _key_ints(key: bytes) -> list[int]:
    k = (key + b"\x00" * 16)[:16]
    return [int.from_bytes(k[i : i + 4], "little") for i in range(0, 16, 4)]


def xxtea_encrypt(data: bytes, key: bytes) -> bytes:
    if len(data) == 0:
        return data
    v = _to_ints(data, True)
    k = _key_ints(key)
    n = len(v)
    rounds = 6 + 52 // n
    s = 0
    z = v[-1]
    for _ in range(rounds):
        s = (s + DELTA) & 0xFFFFFFFF
        e = (s >> 2) & 3
        for p in range(n - 1):
            y = v[p + 1]
            v[p] = (v[p] + _mx(z, y, s, k, p, e)) & 0xFFFFFFFF
            z = v[p]
        y = v[0]
        v[n - 1] = (v[n - 1] + _mx(z, y, s, k, n - 1, e)) & 0xFFFFFFFF
        z = v[n - 1]
    return _to_bytes(v, False)


def xxtea_decrypt(data: bytes, key: bytes) -> bytes | None:
    if len(data) < 8 or len(data) % 4 != 0:
        return None
    v = _to_ints(data, False)
    k = _key_ints(key)
    n = len(v)
    if n < 2:
        return None
    rounds = 6 + 52 // n
    s = (rounds * DELTA) & 0xFFFFFFFF
    y = v[0]
    for _ in range(rounds):
        e = (s >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - _mx(z, y, s, k, p, e)) & 0xFFFFFFFF
            y = v[p]
        z = v[n - 1]
        v[0] = (v[0] - _mx(z, y, s, k, 0, e)) & 0xFFFFFFFF
        y = v[0]
        s = (s - DELTA) & 0xFFFFFFFF
    length = v[-1]
    if length < 0 or length > (n - 1) * 4:
        return None
    return _to_bytes(v, True)


def looks_text(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:2048]
    if sample.startswith(b"\x1f\x8b"):
        return True
    if sample[:1] in (b"{", b"[", b"<") or sample.lstrip()[:8].lower() in (
        b"function",
        b"local ",
        b"var ",
        b"cc.",
    ):
        return True
    nuls = sample.count(0)
    if nuls > len(sample) * 0.05:
        return False
    printable = sum(1 for b in sample if 9 <= b <= 13 or 32 <= b < 127)
    return printable / max(len(sample), 1) > 0.85


def strip_sign(data: bytes) -> tuple[bytes, str]:
    """Cocos often prefixes a short ASCII sign before ciphertext."""
    i = 0
    while i < min(16, len(data)) and 32 <= data[i] < 127 and data[i] not in (0, 10, 13):
        i += 1
    if 2 <= i <= 16 and i < len(data):
        rest = data[i:]
        if len(rest) >= 8:
            return rest, data[:i].decode("ascii", "ignore")
    return data, ""
