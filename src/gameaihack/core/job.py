from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from gameaihack import __version__


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(text: str, maxlen: int = 24) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "game")[:maxlen]


def make_job_id(package_name: str, input_path: Path, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if package_name and package_name != "unknown.pack":
        return package_name
    return slugify(input_path.stem, maxlen=40)


def sha256_file(path: Path, limit: int | None = None) -> str:
    from gameaihack.core.fs import sha256_path

    return sha256_path(path, limit)


class Job:
    def __init__(self, root: Path, job_id: str):
        self.root = root
        self.job_id = job_id
        self.dir = root / job_id

    def mkdir(self) -> None:
        for sub in (
            "raw/unpacked",
            "raw/extract/raw",
            "raw/extract/normalized",
            "raw/ir",
            "raw/deliverable",
            "output/策划",
            "output/美术",
            "output/data",
        ):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)

    def write_json(self, rel: str, data: dict | list) -> Path:
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def run_log_path(self) -> Path:
        return self.dir / "run.log"

    def append_event(self, stage: str, ok: bool, message: str, **extra) -> None:
        rec = {
            "ts": utc_now().isoformat(),
            "stage": stage,
            "ok": ok,
            "message": message,
            **extra,
        }
        with (self.dir / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        from gameaihack.core.progress import log

        flag = "ok" if ok else "FAIL"
        log(f"[{stage}] {flag}  {message}")
        try:
            with (self.dir / "pipeline.log").open("a", encoding="utf-8") as pf:
                pf.write(f"[{rec['ts']}] {flag} {stage}: {message}\n")
        except OSError:
            pass

    def write_manifest(self, **kwargs) -> None:
        path = self.dir / "run_manifest.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {
                "tool_version": __version__,
                "started_at": utc_now().isoformat(),
                "finished_at": None,
                "stages_ok": [],
                "warnings": [],
            }
        data.update(kwargs)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
