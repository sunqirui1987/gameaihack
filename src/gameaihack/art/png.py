from __future__ import annotations

import struct
import zlib
from pathlib import Path


def write_rgba_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    """pixels: RGBA, length width*height*4."""
    if len(pixels) != width * height * 4:
        raise ValueError("pixel buffer size mismatch")
    raw = b"".join(
        b"\x00" + pixels[y * width * 4 : (y + 1) * width * 4] for y in range(height)
    )
    compressed = zlib.compress(raw, 1)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    blob = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


PALETTE = [
    (30, 30, 40, 255),
    (239, 68, 68, 255),
    (34, 197, 94, 255),
    (59, 130, 246, 255),
    (234, 179, 8, 255),
    (168, 85, 247, 255),
    (20, 184, 166, 255),
    (249, 115, 22, 255),
    (244, 114, 182, 255),
    (148, 163, 184, 255),
    (132, 204, 22, 255),
    (14, 165, 233, 255),
    (251, 146, 60, 255),
    (192, 132, 252, 255),
    (74, 222, 128, 255),
    (253, 224, 71, 255),
]


def cell_color(value) -> tuple[int, int, int, int]:
    if value in (0, None, "", " ", ".", 0.0, False):
        return PALETTE[0]
    if isinstance(value, (int, float)):
        return PALETTE[int(value) % (len(PALETTE) - 1) + 1]
    return PALETTE[(hash(str(value)) & 0x7FFFFFFF) % (len(PALETTE) - 1) + 1]


def render_board_png(path: Path, board: list[list], cell: int = 12) -> None:
    if not board or not board[0]:
        write_rgba_png(path, 1, 1, bytes(PALETTE[0]))
        return
    h = len(board)
    w = max(len(row) for row in board)
    cell = max(4, min(cell, 24))
    pw, ph = w * cell, h * cell
    buf = bytearray(pw * ph * 4)
    for y, row in enumerate(board):
        for x in range(w):
            val = row[x] if x < len(row) else 0
            r, g, b, a = cell_color(val)
            for dy in range(cell):
                for dx in range(cell):
                    # 1px grid
                    if dx == 0 or dy == 0:
                        rr, gg, bb = 20, 22, 28
                    else:
                        rr, gg, bb = r, g, b
                    i = ((y * cell + dy) * pw + (x * cell + dx)) * 4
                    buf[i : i + 4] = bytes((rr, gg, bb, 255))
    write_rgba_png(path, pw, ph, bytes(buf))


# 1x1 opaque PNG for fixtures
MIN_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8cfc00000020101d5d2d5d20000000049454e44ae426082"
)
