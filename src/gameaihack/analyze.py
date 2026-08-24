from __future__ import annotations

import json
import sys
from pathlib import Path


def _progress(msg: str) -> None:
    from gameaihack.progress import log

    log(msg)

from gameaihack import __version__
from gameaihack.design import (
    collect_claims,
    mermaid_economy,
    mermaid_flow,
    scan_text_blob,
    score_radar,
    simulate,
)
from gameaihack.extract import run_extract
from gameaihack.fingerprint import scan_paths
from gameaihack.genre import guess_genre
from gameaihack.ingest import PackageInfo, has_remote_catalog, unpack_to, walk_files
from gameaihack.inspect_cmd import inspect_input
from gameaihack.ir import build_ir, validate_ir
from gameaihack.job import Job, make_job_id, sha256_file, utc_now
from gameaihack.layout import art_dir, extract_dir, ir_dir, unpack_dir
from gameaihack.levels import rebuild_levels
from gameaihack.paths import load_yaml
from gameaihack.report import render_deliverable
from gameaihack.runtime import run_runtime
from gameaihack.scoring import input_score, unity_data_present
from gameaihack.loc import extract_loc
from gameaihack.refs import link_references
from gameaihack.tables import discover_tables
from gameaihack.verbs import extract_verbs

STAGES = ["unpack", "fingerprint", "extract", "normalize", "levels", "design", "ai", "report"]


def _should(stage: str, from_stage: str | None) -> bool:
    if not from_stage:
        return True
    if from_stage not in STAGES:
        return True
    return STAGES.index(stage) >= STAGES.index(from_stage)


def analyze(
    input_path: Path,
    *,
    out: Path,
    mode: str = "standard",
    obb: list[Path] | None = None,
    hotupdate: Path | None = None,
    job_id: str | None = None,
    argv: list[str] | None = None,
    thumbs_only: bool = True,
    device: str | None = None,
    from_stage: str | None = None,
    resume: bool = False,
    llm: bool | None = None,
) -> Path:
    input_path = input_path.resolve()
    obb = [p.resolve() for p in (obb or [])]
    out.mkdir(parents=True, exist_ok=True)
    pipe = {}
    try:
        pipe = load_yaml("pipeline.yaml") or {}
    except FileNotFoundError:
        pipe = {}
    adapters = (pipe.get("adapters") or {}) if isinstance(pipe, dict) else {}

    pre = inspect_input(input_path, obb, hotupdate)
    jid = make_job_id(pre.package["name"], input_path, job_id)
    job = Job(out, jid)
    if resume and not job.dir.exists():
        raise ValueError("--resume 需要已存在的 job 目录，并配合 --job-id")
    job.mkdir()
    job.write_manifest(
        mode=mode,
        argv=argv or [],
        thumbs_only=thumbs_only,
        tool_version=__version__,
        from_stage=from_stage,
    )
    job.append_event("inspect", True, f"引擎 {pre.fingerprint.get('engine')}，输入分 {pre.input_profile.get('score')}")
    _progress(f"[1/8] 体检  {pre.fingerprint.get('engine')}  输入分 {pre.input_profile.get('score')}")

    sha = sha256_file(input_path) if input_path.is_file() else ""
    job.write_json(
        "raw/input/sidecars.json",
        {
            "input": str(input_path),
            "sha256": sha,
            "obb": [str(p) for p in obb],
            "hotupdate": str(hotupdate) if hotupdate else None,
        },
    )

    unpacked = unpack_dir(job.dir)
    merged = unpacked / "merged"
    _progress("[2/8] 解包到 raw/ …")
    if merged.exists() and from_stage != "unpack":
        pkg_from_unpack = PackageInfo(name=pre.package["name"])
        job.append_event("unpack", True, "复用 raw/ 已解包")
    else:
        pkg_from_unpack = unpack_to(input_path, unpacked, obb, hotupdate)
        job.append_event("unpack", True, f"已解包到 {unpacked}")

    paths = walk_files(merged)
    size = input_path.stat().st_size if input_path.is_file() else 0
    has_obb = bool(obb) or any(unpacked.joinpath("obb").glob("*"))
    remote = has_remote_catalog(paths, merged)
    fp = scan_paths(
        paths,
        splits=pre.input_profile.get("inner_apks") or [],
        has_obb=has_obb,
        input_bytes=size,
        remote_catalog=remote,
    )
    score, warnings = input_score(
        fp,
        input_bytes=size,
        has_obb=has_obb,
        has_hotupdate=bool(hotupdate and hotupdate.exists()),
        unity_data_present_flag=unity_data_present(paths),
    )

    pkg = PackageInfo(
        name=pkg_from_unpack.name if pkg_from_unpack.name != "unknown.pack" else pre.package["name"],
        version_name=pkg_from_unpack.version_name or pre.package.get("version_name") or "",
        version_code=pkg_from_unpack.version_code or pre.package.get("version_code") or 0,
        source=pkg_from_unpack.source,
    )

    runtime_info = run_runtime(
        merged,
        extract_dir(job.dir) / "runtime",
        device=device if mode == "deep" else None,
        package=pkg.name,
        mode=mode,
    )
    warnings.extend(runtime_info.get("warnings") or [])
    if runtime_info.get("pulled"):
        device_files = extract_dir(job.dir) / "runtime/device_files"
        if device_files.exists():
            for p in device_files.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(device_files)
                    dest = merged / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(p.read_bytes())
            paths = walk_files(merged)
            job.append_event("runtime", True, "已 pull 设备 files 并合并")
    elif device and mode != "deep":
        warnings.append("device_ignored_not_deep")
        job.append_event("runtime", True, "提供了 device 但 mode 不是 deep，已忽略")
    else:
        job.append_event(
            "runtime",
            True,
            f"静态 so 字符串 {runtime_info.get('so_strings', 0)}；key_found={runtime_info.get('key_found')}",
        )

    input_profile = {
        "files": pre.input_profile.get("files") or [],
        "score": score,
        "warnings": warnings,
        "kind": pre.input_profile.get("kind"),
        "inner_apks": pre.input_profile.get("inner_apks") or [],
        "inner_obbs": pre.input_profile.get("inner_obbs") or [],
    }
    job.write_json("raw/fingerprint.json", fp.to_dict())
    job.write_json("raw/input_profile.json", input_profile)
    job.append_event("fingerprint", True, f"引擎 {fp.engine} / {fp.script_backend or '—'}，输入分 {score}")
    _progress(f"[3/8] 指纹  {fp.engine} / {fp.script_backend or '—'}")

    ir = build_ir(job_id=jid, pkg=pkg, fp=fp, sha256=sha, input_profile=input_profile)
    ir["coverage"]["mode"] = mode
    prev_path = ir_dir(job.dir) / "game.ir.json"
    prev = None
    if from_stage and prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = None
        if prev:
            for key in (
                "resources",
                "tables",
                "levels",
                "entity_templates",
                "claims",
                "loc",
                "verbs",
                "ui",
            ):
                if prev.get(key) and not ir.get(key):
                    ir[key] = prev[key]
            if prev.get("coverage"):
                ir["coverage"].update({k: v for k, v in prev["coverage"].items() if k not in {"mode", "tool_version"}})

    norm = extract_dir(job.dir) / "normalized"
    _progress("[4/8] 抽资源 …")
    if _should("extract", from_stage):
        report = run_extract(merged, norm, fp.to_dict(), mode=mode, adapters=adapters)
        job.write_json(
            "raw/extract/report.json",
            {
                "adapter": report.adapter,
                "discovered": report.discovered,
                "exported": len(report.items),
                "encrypted": report.encrypted,
                "warnings": report.warnings,
                "extra": report.extra,
            },
        )
        ir["resources"] = [it.to_resource(i) for i, it in enumerate(report.items)]
        ir["coverage"]["resources"] = {
            "discovered": report.discovered,
            "exported": len(report.items),
            "encrypted": report.encrypted,
            "remote": 1 if fp.remote_catalog else 0,
        }
        ir["unknowns"].extend(report.warnings[:50])
        msg = f"抽出 {len(report.items)} 个资源（发现 {report.discovered}，加密 {report.encrypted}）"
        job.append_event("extract", True, msg)
        _progress(f"[4/8] {msg}")
    else:
        job.append_event("extract", True, "跳过抽取")

    extra_unity = {}
    try:
        extra_unity = json.loads((extract_dir(job.dir) / "report.json").read_text(encoding="utf-8")).get("extra", {}).get("unity", {})
    except Exception:
        extra_unity = {}
    boot_lines = extra_unity.get("boot") or []
    for line in boot_lines:
        if "unityVersion" in line or "=" in line:
            ir["fingerprint"]["engine_version"] = line.split("=")[-1].strip()
            break

    ir["ui"]["screens"] = [
        {"id": r["name"]}
        for r in ir.get("resources") or []
        if any(k in r.get("name", "").lower() for k in ("ui", "panel", "hud", "popup"))
    ][:40]

    boot = merged / "assets/bin/Data/boot.config"
    if boot.exists() and not ir["fingerprint"].get("engine_version"):
        for line in boot.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "unityVersion" in line or line.lower().startswith("android-target"):
                ir["fingerprint"]["engine_version"] = line.split("=", 1)[-1].strip()
                if "unityVersion" in line:
                    break

    for p in list(merged.rglob("catalog.json"))[:5]:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        import re as _re

        urls = _re.findall(r"https?://[^\s\"']+", txt)
        for u in urls[:10]:
            ir["network"]["apis"].append({"id": u, "note": "addressables_catalog"})
        if urls:
            ir["unknowns"].append("addressables_remote_urls_recorded_not_fetched")

    if _should("normalize", from_stage):
        tables = discover_tables(norm, merged)
        ir["tables"] = [{k: v for k, v in t.items() if k != "abs_path"} for t in tables]
        job.write_json("raw/ir/tables_index.json", [{"id": t["id"], "role": t["role"], "rows": t["row_count"]} for t in ir["tables"]])
        ir["coverage"]["tables"] = {
            "decoded": len(ir["tables"]),
            "binary_unknown": 0,
        }
        job.append_event("normalize", True, f"规范化资源 {len(ir['resources'])}，表 {len(ir['tables'])}")
        _progress(f"[5/8] 表 {len(ir['tables'])} 张")
    else:
        tables = []
        job.append_event("normalize", True, "跳过 normalize")

    if _should("levels", from_stage):
        preview_dir = extract_dir(job.dir) / "normalized/maps/previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        levels = rebuild_levels(merged, norm, tables, preview_dir)
        ir["levels"] = levels
        l2 = sum(1 for lv in levels if str(lv.get("rebuild_grade", "L0")) >= "L2")
        ir["coverage"]["levels"] = {"indexed": len(levels), "rebuild_l2_plus": l2}
        job.write_json("raw/ir/levels_index.json", [{"id": lv["id"], "grade": lv.get("rebuild_grade")} for lv in levels])
        job.append_event("levels", True, f"关卡 {len(levels)}，L2+ {l2}")
        _progress(f"[5/8] 关卡 {len(levels)}，L2+ {l2}")
    else:
        job.append_event("levels", True, "跳过关卡")

    ir["genre_guess"] = guess_genre(ir)
    ir["loc"] = extract_loc(norm, merged, ir.get("tables") or [])

    _progress("[6/8] 策划合成 …")
    if _should("design", from_stage):
        blob = scan_text_blob(merged, norm)
        ir["verbs"] = extract_verbs(blob, ir.get("tables") or [], (ir.get("genre_guess") or {}).get("id"))
        ir["claims"] = collect_claims(ir, blob)
        link_references(ir)
        ir["radar"] = score_radar(ir)
        ir["simulations"] = simulate(ir)
        ir["coverage"]["radar"] = ir["radar"]
        ir["coverage"]["design_claims"] = {
            "high": sum(1 for c in ir["claims"] if c.get("confidence") == "high"),
            "medium": sum(1 for c in ir["claims"] if c.get("confidence") == "medium"),
            "low": sum(1 for c in ir["claims"] if c.get("confidence") == "low"),
            "hypothesis": sum(1 for c in ir["claims"] if c.get("severity") == "hypothesis"),
        }
        ir["coverage"]["code"] = {
            "java": "skipped",
            "csharp": "dummy_only" if fp.script_backend == "il2cpp" else "skipped",
            "lua": "ok" if any(r.get("kind") == "script" for r in ir["resources"]) else "missing",
        }
        job.append_event("design", True, f"主张 {len(ir['claims'])} 条，品类 {ir['genre_guess'].get('id')}")
        _progress(f"[6/8] 主张 {len(ir['claims'])} 条，品类 {ir['genre_guess'].get('id')}")
    else:
        job.append_event("design", True, "跳过策划合成")

    diagrams = {
        "loop-session.mmd": mermaid_flow(ir.get("loops", {}).get("session") or [], "session"),
        "loop-day.mmd": mermaid_flow(ir.get("loops", {}).get("day") or [], "day"),
        "loop-meta.mmd": mermaid_flow(ir.get("loops", {}).get("meta") or [], "meta"),
        "economy.mmd": mermaid_economy(ir),
    }
    ddir = extract_dir(job.dir) / "normalized/diagrams"
    ddir.mkdir(parents=True, exist_ok=True)
    for name, body in diagrams.items():
        (ddir / name).write_text(body, encoding="utf-8")

    errs = validate_ir(ir)
    if errs:
        job.write_json("raw/ir/validate_errors.json", errs)
        job.append_event("report", False, "IR 校验失败")
        raise ValueError("IR 校验失败：\n" + "\n".join(errs))
    job.write_json("raw/ir/game.ir.json", ir)
    job.write_json("raw/ir/claims.json", ir["claims"])
    job.write_json("raw/coverage.json", ir["coverage"])

    _progress("[7/8] 抽出游戏贴图，准备 output/ …")
    try:
        from gameaihack.unity_art import ensure_game_art

        n_art = ensure_game_art(job.dir, progress=_progress)
        _progress(f"[7/8] 游戏贴图 {n_art} 张 → {art_dir(job.dir)}")
    except Exception as e:  # noqa: BLE001
        _progress(f"[7/8] 贴图抽出失败：{type(e).__name__}: {e}")

    import os

    pytest_run = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if _should("report", from_stage) and pytest_run:
        render_deliverable(job.dir, ir, thumbs_only=thumbs_only, overwrite_design=True)
        _progress("[7/8] 测试模式：机器稿写入 output/")
    elif _should("report", from_stage):
        render_deliverable(job.dir, ir, thumbs_only=thumbs_only, overwrite_design=False)
        _progress("[7/8] output/美术 已就绪，策划交给 DSH")

    dsh_ok = False
    _progress("[7/8] DSH 读 raw/ 与美术，写 output/策划 …")
    if _should("ai", from_stage):
        from gameaihack.ai_analyze import run_ai_analysis
        from gameaihack.dsh_agent import DshError, require_dsh
        from gameaihack.llm import resolve_llm

        if pytest_run:
            ai = run_ai_analysis(job.dir, ir, cfg=None)
            job.append_event("ai", True, f"测试模式，索引 {ai.get('files', 0)}")
            _progress(f"[7/8] 测试跳过 DSH，索引 {ai.get('files', 0)}")
        else:
            require_dsh()
            cfg = resolve_llm()
            if not cfg:
                raise DshError(
                    "DSH 需要模型密钥。请设 LLM_API_KEY、LLM_BASE_URL、LLM_MODELS（与 llm_bench 相同）。"
                )
            ai = run_ai_analysis(job.dir, ir, cfg=cfg)
            dsh = ai.get("dsh") or {}
            if not dsh.get("ok"):
                raise DshError("DSH 分析 raw/ 失败：\n" + (dsh.get("error") or "未知错误"))
            dsh_ok = True
            job.append_event("ai", True, f"DSH {dsh.get('via')}，文件 {ai.get('files', 0)}")
            _progress(f"[7/8] DSH {dsh.get('via')} 完成，过程见 output/策划/过程.md")
    else:
        job.append_event("ai", True, "跳过 AI")

    _progress("[8/8] 收口 output/ …")
    if _should("report", from_stage):
        from gameaihack.projects import harvest_dsh

        n_h = harvest_dsh(job.dir)
        if dsh_ok:
            render_deliverable(job.dir, ir, thumbs_only=thumbs_only, overwrite_design=False)
            _progress(f"[8/8] DSH 策划已是最终稿（另收 {n_h} 个文件）")
        job.append_event("report", True, "output/ 已生成")
        _progress("[8/8] 工程完成")

    job.write_manifest(
        finished_at=utc_now().isoformat(),
        stages_ok=STAGES,
        warnings=warnings,
    )
    return job.dir
