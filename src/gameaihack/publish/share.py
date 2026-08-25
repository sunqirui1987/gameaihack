from __future__ import annotations

import re
import shutil
import time
import zipfile
from pathlib import Path

from gameaihack.core.job import slugify
from gameaihack.core.layout import ir_dir, output_dir
from gameaihack.publish.projects import PRODUCT_DIRS, PRODUCT_FILES

FORBIDDEN_SUFFIX = {
    ".apk",
    ".xapk",
    ".apks",
    ".aab",
    ".obb",
    ".so",
    ".dll",
    ".exe",
    ".dylib",
}
SECRET_NAME = re.compile(r"(secret|private.?key|\.pem$|\.p12$)", re.I)


class ShareError(Exception):
    pass


def is_forbidden(path: Path) -> bool:
    if path.suffix.lower() in FORBIDDEN_SUFFIX:
        return True
    name = path.name
    if SECRET_NAME.search(name):
        return True
    return False


def share_job(job_dir: Path, dest_zip: Path, *, strict: bool = False) -> dict:
    dest_zip = dest_zip.resolve()
    dest_zip.parent.mkdir(parents=True, exist_ok=True)

    ir_path = ir_dir(job_dir) / "game.ir.json"
    slug = "autopsy"
    if ir_path.exists():
        import json

        ir = json.loads(ir_path.read_text(encoding="utf-8"))
        slug = slugify(ir.get("package", {}).get("name", "") or job_dir.name, maxlen=40)

    items: list[tuple[str, Path]] = _collect_share_items(job_dir)
    if not items:
        raise ShareError(f"没有可分享的策划/美术：{job_dir}")

    skipped: list[str] = []
    added = 0
    stored_suf = {".png", ".jpg", ".jpeg", ".webp", ".ogg", ".mp3", ".mp4", ".zip", ".gz"}
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, f in items:
            if is_forbidden(f):
                skipped.append(rel)
                if strict:
                    raise ShareError(f"strict share 拒绝：{rel}")
                continue
            arc = f"{slug}/{rel}"
            info = zipfile.ZipInfo(filename=arc)
            info.flag_bits |= 0x800
            info.compress_type = zipfile.ZIP_STORED if f.suffix.lower() in stored_suf else zipfile.ZIP_DEFLATED
            info.date_time = time.localtime(f.stat().st_mtime)[:6]
            with f.open("rb") as src, zf.open(info, "w") as dst:
                shutil.copyfileobj(src, dst)
            added += 1
        if skipped:
            zf.writestr(
                f"{slug}/SHARE_EXCLUDED.txt",
                "已排除（可能是原包或密钥）：\n" + "\n".join(skipped) + "\n",
            )

    with zipfile.ZipFile(dest_zip) as zf:
        for n in zf.namelist():
            lower = n.lower()
            if any(lower.endswith(s) for s in (".apk", ".so", ".obb", ".xapk", ".dll")):
                raise ShareError(f"消毒失败，zip 内仍有 {n}")

    return {"zip": str(dest_zip), "added": added, "skipped": skipped, "slug": slug}


def _collect_share_items(job_dir: Path) -> list[tuple[str, Path]]:
    """解压后就是 output/ 工程。不含 raw/。"""
    items: list[tuple[str, Path]] = []
    out = output_dir(job_dir)
    if (out / "README.md").is_file() or (out / "策划").is_dir():
        for f in out.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                items.append((f"output/{f.relative_to(out).as_posix()}", f))
        readme = job_dir / "README.md"
        if readme.is_file():
            items.append(("README.md", readme))
        return items
    if (job_dir / "AGENTS.md").is_file():
        for name in PRODUCT_FILES:
            p = job_dir / name
            if p.is_file():
                items.append((name, p))
        for name in PRODUCT_DIRS:
            root = job_dir / name
            if not root.is_dir():
                continue
            for f in root.rglob("*"):
                if f.is_file():
                    items.append((f"{name}/{f.relative_to(root).as_posix()}", f))
        return items
    from gameaihack.core.layout import raw_dir

    deliverable = raw_dir(job_dir) / "deliverable"
    if deliverable.is_dir():
        for f in deliverable.rglob("*"):
            if f.is_file():
                items.append((f.relative_to(deliverable).as_posix(), f))
    return items
