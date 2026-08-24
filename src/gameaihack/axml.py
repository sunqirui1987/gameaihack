from __future__ import annotations

import struct
from xml.etree import ElementTree as ET

RES_XML = 0x0003
RES_STRING_POOL = 0x0001
RES_XML_START_ELEMENT = 0x0102


def parse_manifest_bytes(data: bytes) -> dict:
    empty = {"name": "unknown.pack", "version_name": "", "version_code": 0, "source": "fallback"}
    if not data:
        return empty
    stripped = data.lstrip()
    if stripped[:1] == b"<" or stripped[:2] == b"<?":
        return _from_text(stripped) or empty
    try:
        return _from_binary(data) or empty
    except (struct.error, IndexError, ValueError, UnicodeDecodeError):
        return empty


def parse_manifest_apk(apk_path) -> dict:
    import zipfile
    from pathlib import Path

    path = Path(apk_path)
    try:
        with zipfile.ZipFile(path) as z:
            blob = z.read("AndroidManifest.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        return {"name": "unknown.pack", "version_name": "", "version_code": 0, "source": "fallback"}
    info = parse_manifest_bytes(blob)
    if info.get("name") != "unknown.pack":
        info["source"] = info.get("source") or "axml"
    return info


def _from_text(data: bytes) -> dict | None:
    text = data.decode("utf-8", "ignore")
    pkg = _attr(text, "package") or "unknown.pack"
    vn = _attr(text, "android:versionName") or _attr(text, "versionName") or ""
    vc = _attr(text, "android:versionCode") or _attr(text, "versionCode") or "0"
    try:
        code = int(str(vc), 0)
    except ValueError:
        code = 0
    if pkg == "unknown.pack":
        try:
            cleaned = text.replace("android:", "")
            root = ET.fromstring(cleaned)
            pkg = root.attrib.get("package") or pkg
        except ET.ParseError:
            return None
    return {"name": pkg, "version_name": str(vn), "version_code": code, "source": "xml"}


def _attr(text: str, name: str) -> str | None:
    import re

    m = re.search(rf'\b{re.escape(name)}="([^"]+)"', text)
    return m.group(1) if m else None


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _from_binary(data: bytes) -> dict | None:
    if len(data) < 16:
        return PackageInfo()
    # Some files are 0x00080003 as packed type+headersize
    pool_off = None
    off = 0
    # skip xml file header
    ftype = _u16(data, 0)
    fhs = _u16(data, 2)
    if ftype == RES_XML:
        off = fhs
    else:
        off = 8
    strings: list[str] = []
    while off + 8 <= len(data):
        ctype = _u16(data, off)
        chs = _u16(data, off + 2)
        csize = _u32(data, off + 4)
        if csize < 8 or off + csize > len(data):
            break
        if ctype == RES_STRING_POOL:
            strings = _read_string_pool(data, off)
            pool_off = off
        elif ctype == RES_XML_START_ELEMENT:
            pkg = _start_element_package(data, off, chs, strings)
            if pkg:
                return pkg
        off += csize
        if csize % 4:
            off += 4 - (csize % 4)
    # fallback: scan strings for dotted package name
    if pool_off is not None:
        for s in strings:
            if s.count(".") >= 1 and s.replace(".", "").isalnum() and not s.startswith("http") and len(s) < 80:
                if s.startswith("com.") or s.startswith("org.") or s.startswith("net.") or s.startswith("io."):
                    return {"name": s, "version_name": "", "version_code": 0, "source": "axml-string"}
    return None


def _read_string_pool(data: bytes, off: int) -> list[str]:
    # header: type, headerSize, size, stringCount, styleCount, flags, stringsStart, stylesStart
    string_count = _u32(data, off + 8)
    flags = _u32(data, off + 16)
    strings_start = _u32(data, off + 20)
    utf8 = bool(flags & (1 << 8))
    out: list[str] = []
    for i in range(min(string_count, 40000)):
        idx_off = off + 28 + i * 4
        if idx_off + 4 > len(data):
            break
        s_off = _u32(data, idx_off) + off + strings_start
        if s_off + 2 > len(data):
            out.append("")
            continue
        try:
            if utf8:
                # utf8: u8len, u8bytelen, bytes, 0
                _nchars = data[s_off]
                nbytes = data[s_off + 1]
                start = s_off + 2
                # if high bit, two-byte length
                if _nchars & 0x80:
                    nbytes = data[s_off + 3]
                    start = s_off + 4
                raw = data[start : start + nbytes]
                out.append(raw.decode("utf-8", "replace"))
            else:
                slen = _u16(data, s_off)
                raw = data[s_off + 2 : s_off + 2 + slen * 2]
                out.append(raw.decode("utf-16-le", "replace"))
        except (IndexError, UnicodeDecodeError, struct.error):
            out.append("")
    return out


def _start_element_package(data: bytes, off: int, header_size: int, strings: list[str]) -> dict | None:
    # after header: ns, name, attrStart, attrSize, attrCount, idIndex, classIndex, styleIndex
    body = off + header_size
    if body + 20 > len(data):
        return None
    name_idx = _u32(data, body + 4)
    attr_count = _u16(data, body + 12)
    name = strings[name_idx] if 0 <= name_idx < len(strings) else ""
    if name != "manifest":
        return None
    attr_off = off + header_size + 20
    pkg = "unknown.pack"
    vn = ""
    vc = 0
    for i in range(attr_count):
        a = attr_off + i * 20
        if a + 20 > len(data):
            break
        aname = _u32(data, a + 4)
        raw_value = _u32(data, a + 8)
        vtype = data[a + 15] if a + 15 < len(data) else 0
        data_val = _u32(data, a + 16)
        key = strings[aname] if 0 <= aname < len(strings) else ""
        if key == "package":
            if 0 <= raw_value < len(strings):
                pkg = strings[raw_value]
            elif 0 <= data_val < len(strings) and vtype == 0x03:
                pkg = strings[data_val]
        elif key == "versionName":
            if vtype == 0x03 and 0 <= data_val < len(strings):
                vn = strings[data_val]
            elif 0 <= raw_value < len(strings):
                vn = strings[raw_value]
        elif key == "versionCode":
            vc = data_val
    if pkg and pkg != "unknown.pack":
        return {"name": pkg, "version_name": vn, "version_code": int(vc), "source": "axml"}
    return None
