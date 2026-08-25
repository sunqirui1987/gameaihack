from __future__ import annotations

import re
from pathlib import Path

_PAT: dict[int, re.Pattern[bytes]] = {}


def _ascii_re(min_len: int) -> re.Pattern[bytes]:
    n = max(1, int(min_len))
    pat = _PAT.get(n)
    if pat is None:
        pat = re.compile(rb"[\x20-\x7e]{" + str(n).encode("ascii") + rb",}")
        _PAT[n] = pat
    return pat


def iter_ascii_strings(data: bytes, min_len: int = 4):
    """C-speed scan. Long runs are split so a key at offset 300 is not dropped."""
    for m in _ascii_re(min_len).finditer(data):
        s = m.group().decode("ascii")
        if len(s) <= 256:
            yield s
            continue
        for i in range(0, len(s), 256):
            chunk = s[i : i + 256]
            if len(chunk) >= min_len:
                yield chunk


def strings_from_file(path: Path, limit: int = 8 * 1024 * 1024, min_len: int = 4) -> list[str]:
    try:
        with path.open("rb") as f:
            data = f.read(limit)
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
