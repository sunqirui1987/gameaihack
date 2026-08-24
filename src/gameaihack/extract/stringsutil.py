from __future__ import annotations

from pathlib import Path


def iter_ascii_strings(data: bytes, min_len: int = 4):
    buf = bytearray()
    for b in data:
        if 32 <= b < 127:
            buf.append(b)
        else:
            if len(buf) >= min_len:
                yield buf.decode("ascii")
            buf.clear()
    if len(buf) >= min_len:
        yield buf.decode("ascii")


def strings_from_file(path: Path, limit: int = 8 * 1024 * 1024, min_len: int = 4) -> list[str]:
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return []
    return list(iter_ascii_strings(data, min_len))


def nearby_keys(strings: list[str]) -> list[str]:
    """Candidates for XXTEA keys: strings near crypto markers, or 6–16 ascii tokens."""
    markers = ("xxtea", "xxte", "sign", "crypt", "decrypt", "aes", "tea")
    out: list[str] = []
    lower = [s.lower() for s in strings]
    for i, s in enumerate(strings):
        sl = lower[i]
        if any(m in sl for m in markers):
            for j in range(max(0, i - 4), min(len(strings), i + 5)):
                cand = strings[j]
                if 6 <= len(cand) <= 16 and cand.isascii() and cand not in out:
                    out.append(cand)
    for s in strings:
        if 8 <= len(s) <= 16 and s.isalnum() and s not in out:
            out.append(s)
        if len(out) > 40:
            break
    return out[:40]
