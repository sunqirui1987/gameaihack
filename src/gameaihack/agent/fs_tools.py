"""Job 目录内的文件工具。只读写本包，不碰 raw 以外的仓库。"""

from __future__ import annotations

import re
from pathlib import Path

from gameaihack.core.fs import iter_files

WRITE_ROOTS = ("output/策划", "output/复刻说明.md", "清单.md", "清单", "AGENTS.md")
SKIP_GREP = {".png", ".jpg", ".jpeg", ".webp", ".ogg", ".mp3", ".mp4", ".so", ".apk", ".bundle", ".unity3d"}


def job_path(job_dir: Path, rel: str) -> Path:
    job = Path(job_dir).resolve()
    raw = str(rel or "").strip() or "."
    cand = Path(raw)
    if cand.is_absolute():
        text = str(cand)
        job_s = str(job)
        if text == job_s or text.startswith(job_s + "/"):
            p = cand.resolve()
        else:
            for mark in ("/output/", "/raw/", "/清单.md", "/清单/"):
                i = text.find(mark)
                if i >= 0:
                    p = (job / text[i + 1 :]).resolve()
                    break
            else:
                p = (job / cand.name).resolve()
    else:
        p = (job / raw).resolve()
    try:
        p.relative_to(job)
    except ValueError as e:
        raise PermissionError(f"路径超出 job：{rel}") from e
    return p


def _can_write(job_dir: Path, path: Path) -> bool:
    job = Path(job_dir).resolve()
    rel = path.relative_to(job).as_posix()
    if rel == "AGENTS.md" or rel == "清单.md":
        return True
    if rel.startswith("清单/"):
        return True
    if rel == "output/复刻说明.md" or rel.startswith("output/策划/"):
        return True
    return False


def read_file(job_dir: Path, path: str, offset: int = 1, limit: int = 400) -> str:
    p = job_path(job_dir, path)
    if not p.is_file():
        return f"没有这个文件：{path}"
    if p.suffix.lower() in SKIP_GREP:
        return f"二进制不读：{p.relative_to(job_dir).as_posix()}（{p.stat().st_size} bytes）"
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    off = max(1, int(offset or 1))
    lim = max(1, min(int(limit or 400), 800))
    chunk = lines[off - 1 : off - 1 + lim]
    body = "\n".join(chunk)
    if len(body) > 80_000:
        body = body[:80_000] + "\n…截断"
    return f"{p.relative_to(job_dir).as_posix()}  L{off}-{off + len(chunk) - 1}/{len(lines)}\n{body}"


def write_file(job_dir: Path, path: str, content: str) -> str:
    p = job_path(job_dir, path)
    if not _can_write(job_dir, p):
        return f"拒绝写入 {path}。只能写 output/策划/、清单.md、清单/。"
    if p.name == "_事实源.md":
        return "拒绝改 _事实源.md，那是机器事实源。"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    return f"已写 {p.relative_to(job_dir).as_posix()}（{len(content)} 字）"


def _count_files(folder: Path, cap: int = 5000) -> int:
    n = 0
    try:
        for child in folder.iterdir():
            if child.name.startswith("."):
                continue
            if child.is_file():
                n += 1
            elif child.is_dir():
                n += _count_files(child, cap)
            if n >= cap:
                return n
    except OSError:
        return n
    return n


def list_dir(job_dir: Path, path: str = ".") -> str:
    """列目录：子目录带文件数，文件多时只给样本。"""
    p = job_path(job_dir, path or ".")
    if not p.exists():
        return f"没有：{path}"
    if p.is_file():
        st = p.stat()
        return f"{p.relative_to(job_dir).as_posix()}  {st.st_size} bytes"
    dirs: list[Path] = []
    files: list[Path] = []
    try:
        for c in p.iterdir():
            if c.name.startswith("."):
                continue
            (dirs if c.is_dir() else files).append(c)
    except OSError as e:
        return f"读目录失败：{e}"
    dirs.sort(key=lambda x: x.name.lower())
    files.sort(key=lambda x: x.name.lower())
    rows = [f"{p.relative_to(job_dir).as_posix()}/"]
    for d in dirs[:60]:
        n = _count_files(d)
        extra = "+" if n >= 5000 else ""
        rows.append(f"  {d.name}/  {n}{extra} files")
    if len(dirs) > 60:
        rows.append(f"  …还有 {len(dirs) - 60} 个目录")
    if len(files) <= 24:
        for f in files:
            rows.append(f"  {f.name}")
    else:
        for f in files[:8]:
            rows.append(f"  {f.name}")
        rows.append(f"  …共 {len(files)} 个文件（用 glob 按扩展名筛）")
    return "\n".join(rows)


def glob_files(job_dir: Path, pattern: str, path: str = ".") -> str:
    import fnmatch

    root = job_path(job_dir, path or ".")
    job = Path(job_dir).resolve()
    pat = (pattern or "*").strip()
    hits: list[str] = []
    base = root if root.is_dir() else root.parent
    for f in iter_files(base):
        try:
            rel = f.relative_to(job).as_posix()
            inner = f.relative_to(base).as_posix()
        except ValueError:
            continue
        if (
            fnmatch.fnmatch(rel, pat)
            or fnmatch.fnmatch(inner, pat)
            or fnmatch.fnmatch(f.name, pat)
            or fnmatch.fnmatch("/" + inner, pat)
        ):
            suf = "/" if f.is_dir() else ""
            hits.append(rel + suf)
        if len(hits) >= 80:
            break
    if not hits:
        return f"没有匹配 `{pat}`"
    more = ""
    if len(hits) >= 80:
        more = "\n…最多 80 条"
    return "\n".join(hits) + more


def tree(job_dir: Path, path: str = ".", depth: int = 2) -> str:
    root = job_path(job_dir, path or ".")
    job = Path(job_dir).resolve()
    depth = max(1, min(int(depth or 2), 4))
    lines: list[str] = []

    def walk(cur: Path, d: int, prefix: str) -> None:
        if len(lines) >= 120:
            return
        try:
            kids = [c for c in cur.iterdir() if not c.name.startswith(".")]
        except OSError:
            return
        kids.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
        files = [c for c in kids if c.is_file()]
        dirs = [c for c in kids if c.is_dir()]
        if d >= depth:
            if dirs or files:
                lines.append(f"{prefix}… {len(dirs)} dirs / {len(files)} files")
            return
        for sub in dirs[:40]:
            n = _count_files(sub)
            lines.append(f"{prefix}{sub.name}/  ({n})")
            walk(sub, d + 1, prefix + "  ")
        if len(dirs) > 40:
            lines.append(f"{prefix}… +{len(dirs) - 40} dirs")
        if len(files) <= 12:
            for f in files:
                lines.append(f"{prefix}{f.name}")
        elif files:
            lines.append(f"{prefix}[{len(files)} files]")

    rel = root.relative_to(job).as_posix() if root != job else "."
    lines.append(rel + ("/" if root.is_dir() else ""))
    if root.is_dir():
        walk(root, 0, "  ")
    return "\n".join(lines)


def search_replace(job_dir: Path, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    p = job_path(job_dir, path)
    if not _can_write(job_dir, p):
        return f"拒绝改 {path}"
    if p.name == "_事实源.md":
        return "拒绝改 _事实源.md"
    if not p.is_file():
        return f"没有这个文件：{path}"
    text = p.read_text(encoding="utf-8")
    if not old_string:
        return "old_string 为空"
    n = text.count(old_string)
    if n == 0:
        return "没有匹配到 old_string"
    if n > 1 and not replace_all:
        return f"匹配 {n} 处，请把 old_string 写得更唯一，或 replace_all=true"
    if replace_all:
        p.write_text(text.replace(old_string, new_string), encoding="utf-8")
        return f"已替换 {n} 处 {p.relative_to(job_dir).as_posix()}"
    p.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
    return f"已替换 1 处 {p.relative_to(job_dir).as_posix()}"


def grep_files(job_dir: Path, pattern: str, path: str = "raw") -> str:
    root = job_path(job_dir, path or "raw")
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"正则无效：{e}"
    hits: list[str] = []
    files = [root] if root.is_file() else list(iter_files(root, skip_dirs={"美术", "textures"}))
    for f in files:
        if f.suffix.lower() in SKIP_GREP:
            continue
        try:
            if f.stat().st_size > 2_000_000:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                rel = f.relative_to(job_dir).as_posix()
                hits.append(f"{rel}:{i}:{line[:200]}")
                if len(hits) >= 40:
                    return "\n".join(hits) + "\n…截断"
    return "\n".join(hits) or "没有匹配"


def _fn(name: str, desc: str, props: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props,
                **({"required": required} if required else {}),
            },
        },
    }


SCHEMAS = [
    _fn(
        "read_file",
        "读 job 内文本。大文件用 offset/limit 分页。不要读 png/so。",
        {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}},
        ["path"],
    ),
    _fn(
        "write",
        "整文件写入。只能写 output/策划/ 或 清单.md / 清单/。",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _fn(
        "search_replace",
        "改已有策划文件中的一段文字。old_string 必须在文件里唯一，除非 replace_all。",
        {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        ["path", "old_string", "new_string"],
    ),
    _fn(
        "list_dir",
        "列目录。子目录带文件数；文件很多时只给样本。看美术请先 list_dir output/美术 看文件夹，不要枚举上万 png。",
        {"path": {"type": "string"}},
    ),
    _fn(
        "tree",
        "有限深度目录树。depth 默认 2，最大 4。适合先摸 raw/ 和 output/ 结构。",
        {"path": {"type": "string"}, "depth": {"type": "integer"}},
    ),
    _fn(
        "glob",
        "按 glob 找文件，例如 **/*.md、*.json、raw/ir/*。最多 80 条。",
        {"pattern": {"type": "string"}, "path": {"type": "string"}},
        ["pattern"],
    ),
    _fn(
        "grep",
        "在文本里正则搜索。默认 path=raw。不要对 output/美术 做 grep。",
        {"pattern": {"type": "string"}, "path": {"type": "string"}},
        ["pattern"],
    ),
]


def run_tool(job_dir: Path, name: str, args: dict) -> str:
    try:
        if name in {"read_file", "read"}:
            return read_file(
                job_dir,
                str(args.get("path") or ""),
                int(args.get("offset") or 1),
                int(args.get("limit") or 400),
            )
        if name in {"write", "write_file"}:
            return write_file(job_dir, str(args.get("path") or ""), str(args.get("content") or ""))
        if name in {"search_replace", "str_replace"}:
            return search_replace(
                job_dir,
                str(args.get("path") or ""),
                str(args.get("old_string") or ""),
                str(args.get("new_string") or ""),
                bool(args.get("replace_all")),
            )
        if name in {"list_dir", "ls"}:
            return list_dir(job_dir, str(args.get("path") or "."))
        if name == "tree":
            return tree(job_dir, str(args.get("path") or "."), int(args.get("depth") or 2))
        if name in {"glob", "glob_file_search"}:
            return glob_files(job_dir, str(args.get("pattern") or "*"), str(args.get("path") or "."))
        if name == "grep":
            return grep_files(job_dir, str(args.get("pattern") or ""), str(args.get("path") or "raw"))
        return f"未知工具 {name}。可用：read_file write search_replace list_dir tree glob grep"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"
