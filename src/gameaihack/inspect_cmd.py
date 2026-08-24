from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from gameaihack.fingerprint import Fingerprint, scan_paths
from gameaihack.ingest import IngestError, has_remote_catalog, logical_paths
from gameaihack.scoring import input_score, unity_data_present


@dataclass
class InspectResult:
    package: dict
    fingerprint: dict
    input_profile: dict
    file_count: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_text(self) -> str:
        fp = self.fingerprint
        ip = self.input_profile
        lines = [
            f"包名: {self.package.get('name')}  版本 {self.package.get('version_name') or '—'} ({self.package.get('version_code') or '—'})",
            f"引擎: {fp.get('engine')}  {fp.get('script_backend') or '—'}",
            f"保护: {', '.join(fp.get('protection') or []) or 'none'}",
            f"热更: {', '.join(fp.get('hotupdate') or []) or 'none'}",
            f"输入分: {ip.get('score')}/100",
            f"命中规则: {', '.join(fp.get('matched_rules') or []) or '—'}",
            f"文件条目: {self.file_count}",
            f"shell_likely: {fp.get('shell_likely')}",
        ]
        warns = ip.get("warnings") or []
        if warns:
            lines.append("警告:")
            for w in warns:
                lines.append(f"  - {w}")
        else:
            lines.append("警告: 无")
        if ip.get("score", 100) < 60:
            lines.append("下一步: 补 OBB / 完整 XAPK / --hotupdate 后再 analyze。不补也可以继续，但覆盖率会很低。")
        return "\n".join(lines) + "\n"


def inspect_input(
    input_path: Path,
    obb: list[Path] | None = None,
    hotupdate: Path | None = None,
) -> InspectResult:
    input_path = input_path.resolve()
    if not input_path.exists():
        raise IngestError(f"找不到输入：{input_path}")
    obb = [p.resolve() for p in (obb or [])]
    paths, meta, pkg = logical_paths(input_path, obb, hotupdate)
    size = input_path.stat().st_size if input_path.is_file() else 0
    has_obb = bool(meta.inner_obbs or obb)
    remote = has_remote_catalog(paths, None)
    fp = scan_paths(
        paths,
        splits=[Path(n).stem for n in meta.inner_apks],
        has_obb=has_obb,
        input_bytes=size,
        remote_catalog=remote,
    )
    score, warnings = input_score(
        fp,
        input_bytes=size,
        has_obb=has_obb,
        has_hotupdate=bool(hotupdate and hotupdate.exists() and any(hotupdate.iterdir())),
        unity_data_present_flag=unity_data_present(paths),
    )
    profile = {
        "files": meta.files,
        "score": score,
        "warnings": warnings,
        "kind": meta.kind,
        "inner_apks": meta.inner_apks,
        "inner_obbs": meta.inner_obbs,
    }
    return InspectResult(
        package={
            "name": pkg.name,
            "version_name": pkg.version_name,
            "version_code": pkg.version_code,
            "source": pkg.source,
        },
        fingerprint=fp.to_dict(),
        input_profile=profile,
        file_count=len(paths),
        warnings=warnings,
    )
