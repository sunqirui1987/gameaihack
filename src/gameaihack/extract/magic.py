from __future__ import annotations

import math
from collections import Counter


def sniff(data: bytes) -> str | None:
    if not data:
        return None
    if data.startswith(b"\x89PNG"):
        return "texture"
    if data.startswith(b"\xff\xd8\xff"):
        return "texture"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "texture"
    if data.startswith(b"OggS"):
        return "audio"
    if data.startswith(b"RIFF") and b"WAVE" in data[:16]:
        return "audio"
    if data.startswith(b"ID3") or data[:2] == b"\xff\xfb":
        return "audio"
    if data.startswith(b"\x1a\x45\xdf\xa3") or data[4:8] == b"ftyp":
        return "video"
    if data.startswith(b"\x1bLua"):
        return "script"
    if data[:1] in (b"{", b"[") or data.lstrip()[:1] in (b"{", b"["):
        return "config"
    if data.lstrip()[:5] == b"<?xml" or data.lstrip()[:1] == b"<":
        return "config"
    if data.startswith(b"PK\x03\x04"):
        return "other"
    return None


def suffix_for_kind(kind: str, data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data.startswith(b"OggS"):
        return ".ogg"
    if data.startswith(b"\x1bLua"):
        return ".luac"
    if kind == "config" and data.lstrip()[:1] in (b"{", b"["):
        return ".json"
    if kind == "config":
        return ".xml"
    return ".bin"


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    n = len(data)
    c = Counter(data)
    return -sum((v / n) * math.log2(v / n) for v in c.values())
