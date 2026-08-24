from __future__ import annotations

import re


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    p = pattern.replace("\\", "/")
    out: list[str] = []
    i = 0
    while i < len(p):
        if p.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif p.startswith("**", i):
            out.append(".*")
            i += 2
        elif p[i] == "*":
            out.append("[^/]*")
            i += 1
        elif p[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(p[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


def match_glob(path: str, pattern: str) -> bool:
    path = path.replace("\\", "/").lstrip("./")
    return glob_to_regex(pattern).match(path) is not None
