"""用 DSH + LLM 读解包原始文件，写出策划文档。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from gameaihack.agent.corpus import batch_text, index_markdown, iter_source_files
from gameaihack.agent.dsh import run_dsh
from gameaihack.core.layout import art_dir, design_dir, raw_dir
from gameaihack.agent.llm import LlmConfig, chat, resolve_llm

SYSTEM = (
    "你是游戏策划。输入是从安装包解出来的原始文本。"
    "用中文写给人看的策划摘要：这是什么游戏、怎么玩、关卡怎么排、怎么赚钱。"
    "不要写 Unity 类名、程序集、文件路径、「来源：」。"
    "不要写盗版客户端、外挂、密钥。广告 SDK / Firebase 忽略。"
)

USER_TMPL = """游戏 `{pkg}`，引擎 {engine}，品类猜测 {genre}。
已索引关卡 {n_lv}，表 {n_tb}，资源 {n_res}。

下面是原始文件摘录。请输出 JSON（不要 markdown 围栏）：
{{
  "summary": "一句话这是什么游戏",
  "genre": "品类",
  "systems": [{{"name": "", "detail": "", "path": ""}}],
  "levels": "关卡怎么组织",
  "economy": "经济/商业化",
  "unknowns": ["还缺什么"],
  "gdd_markdown": "给策划看的一章完整 markdown"
}}

{batch}
"""

DSH_PROMPT = """工作区根目录是 jobs/<包名>。

目标：output/策划/ + output/美术/ 合在一起，足够用别的引擎重做一版玩法相同的游戏。

你要：读懂 raw/ 和 output/美术/，写出完整策划到 output/策划/。
- raw/：解包数据（配置、关卡索引、manifest、文本）
- output/美术/：抽出的 PNG（角色、服装、界面、场景、礼包、头像…）
- output/策划/：最终成品，你写的就是最后一稿

策划必须把美术整合进去：正文嵌图，并写 图鉴/（角色、服装、界面、场景、礼包），每张图注明用在哪个系统。

过程：每读一个文件、每写一个文件，先用一句话说你在做什么。

写法：给人看的正式 GDD。嵌 markdown 图片，例如 `![](../美术/角色/redbird.png)`。
不要写 Unity 类名、程序集、「来源：」。不要编造每关猪的坐标。
不要往美术目录拷二进制。不要写盗版客户端。
"""


def _art_overview(job_dir: Path, limit: int = 36) -> str:
    art = art_dir(job_dir)
    if not art.is_dir():
        return "（还没有抽出 PNG）"
    lines: list[str] = []
    for folder in sorted(p for p in art.iterdir() if p.is_dir()):
        pngs = list(folder.rglob("*.png"))
        if not pngs:
            continue
        sample = "、".join(p.name for p in pngs[:4])
        lines.append(f"- `{folder.name}/` {len(pngs)} 张，例如 {sample}")
        if len(lines) >= limit:
            break
    return "\n".join(lines) or "（美术目录是空的）"


def _chapter_list(ir: dict) -> list[int]:
    chs: set[int] = set()
    for lv in ir.get("levels") or []:
        extra = lv.get("extra") or {}
        c = extra.get("chapter")
        if c is None:
            continue
        try:
            chs.add(int(c))
        except (TypeError, ValueError):
            continue
    return sorted(chs)


def dsh_book_tasks(job_dir: Path, ir: dict) -> list[tuple[str, str]]:
    """DSH 分步：先全书，再按章关卡。每一步都要读 raw 和美术。"""
    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    n_lv = len(ir.get("levels") or [])
    chapters = _chapter_list(ir)
    n_ch = len(chapters) or 0
    art = _art_overview(job_dir)
    head = (
        DSH_PROMPT
        + f"\n游戏 `{pkg}`。已索引关卡 {n_lv}，章节 {n_ch}。\n\n"
        + f"美术目录现在有：\n{art}\n\n"
        + "先读 raw/AGENTS.md、raw/ir/、raw/fingerprint.json，再 ls output/美术/。\n"
    )
    tasks = [
        (
            "全书策划",
            head
            + "请写出完整策划正文到 output/策划/，当作重做说明书：\n"
            + "- README.md（怎么用这份策划 + 美术重做游戏）\n"
            + "- 00-封面.md 01-产品定位.md 02-核心玩法.md 03-关卡设计.md\n"
            + "- 04-成长与进度.md 05-经济与商业化.md 06-系统总表.md\n"
            + "- 07-新手-UI-社交.md 08-技术约束.md 09-未知与下一步.md\n"
            + "封面、玩法、大厅必须嵌角色/界面图。写完列出文件。\n",
        ),
        (
            "美术图鉴",
            head
            + "把 output/美术/ 整合成策划图鉴，写到 output/策划/图鉴/：\n"
            + "- 图鉴/README.md 重做对照表：系统 → 美术目录 → 怎么用\n"
            + "- 图鉴/角色.md 图鉴/服装.md 图鉴/界面.md 图鉴/场景.md\n"
            + "- 图鉴/礼包.md 图鉴/头像.md\n"
            + "每张图写：文件名、用在哪个界面/角色/关卡。服装按套装分组。\n"
            + "图用 markdown 引用，不要复制二进制。\n",
        ),
        (
            "关卡策划",
            head
            + f"请按章写出关卡策划到 output/策划/关卡/。共 {n_ch or '若干'} 章。\n"
            + "- 关卡/README.md 目录\n"
            + "- 每一章一个文件：关卡/第001章.md、第002章.md …\n"
            + "每章写：这一章干什么、怎么玩、关卡表，并嵌对应场景/角色图。\n"
            + "不要空 JSON，不要资源路径表。写完列出文件数量。\n",
        ),
    ]
    return tasks


def run_dsh_book(job_dir: Path, ir: dict, cfg: LlmConfig) -> dict:
    """用 DSH 读 raw + 美术，写出全部策划。过程写到 策划/过程.md 和 raw/dsh.log。"""
    from datetime import datetime, timezone

    from gameaihack.core.progress import log

    dest = design_dir(job_dir)
    dest.mkdir(parents=True, exist_ok=True)
    journal = dest / "过程.md"
    tasks = dsh_book_tasks(job_dir, ir)
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    journal.write_text(
        f"# DSH 提取过程\n\n开始 {started}。共 {len(tasks)} 步：读 raw/ 与 output/美术/，写 output/策划/。\n",
        encoding="utf-8",
    )

    def note(msg: str) -> None:
        line = msg.rstrip()
        if not line:
            return
        with journal.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    results: list[dict] = []
    all_ok = True
    for i, (title, prompt) in enumerate(tasks, 1):
        banner = f"[dsh] ========== {i}/{len(tasks)} {title} =========="
        log(banner)
        note(f"\n## {i}/{len(tasks)} {title}\n")
        note(f"开始 {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n")
        dsh = run_dsh(job_dir, prompt, cfg, timeout=1800, on_line=note)
        results.append({"title": title, "ok": dsh.get("ok"), "error": dsh.get("error")})
        if dsh.get("ok"):
            note(f"\n本步完成。\n")
        else:
            all_ok = False
            note(f"\n本步失败：{dsh.get('error') or 'unknown'}\n")
            break
    journal.write_text(
        journal.read_text(encoding="utf-8")
        + f"\n## 结束\n\n全部成功：{all_ok}。过程日志同时在 `../../raw/dsh.log`。\n",
        encoding="utf-8",
    )
    err = next((r.get("error") for r in results if not r.get("ok")), "")
    return {"ok": all_ok, "via": "cli", "error": err or "", "steps": results}


def run_ai_analysis(job_dir: Path, ir: dict, *, cfg: LlmConfig | None = None) -> dict:
    """写入 策划/ai/，并把摘要挂到 ir['ai_analysis']。失败不抛给整条管线。"""
    cfg = cfg or resolve_llm()
    dest = design_dir(job_dir) / "ai"
    dest.mkdir(parents=True, exist_ok=True)
    files = iter_source_files(job_dir)
    (dest / "文件索引.md").write_text(index_markdown(job_dir, files), encoding="utf-8")
    result: dict = {
        "files": len(files),
        "dsh": None,
        "llm": None,
        "ok": False,
    }
    if not files:
        (dest / "原始文件分析.md").write_text("# 原始文件分析\n\n没有可送进模型的文本文件。\n", encoding="utf-8")
        ir["ai_analysis"] = result
        return result

    _ensure_raw_agents(job_dir)
    import os

    if cfg and not os.environ.get("PYTEST_CURRENT_TEST"):
        from gameaihack.core.progress import log

        log(f"[dsh] 准备读 raw/ 和 output/美术/，索引文件 {len(files)} 个")
        dsh = run_dsh_book(job_dir, ir, cfg)
        result["dsh"] = {
            "ok": dsh.get("ok"),
            "via": dsh.get("via"),
            "error": dsh.get("error"),
            "steps": dsh.get("steps"),
        }
        if dsh.get("text"):
            (dest / "dsh.md").write_text("# DSH\n\n" + str(dsh["text"]) + "\n", encoding="utf-8")
        if dsh.get("ok"):
            result["ok"] = True
        elif dsh.get("error"):
            (dest / "dsh.error.txt").write_text(str(dsh["error"]), encoding="utf-8")

    if cfg:
        try:
            parsed = _llm_pass(job_dir, ir, files, cfg)
            result["llm"] = {"ok": True, "model": cfg.model}
            result["ok"] = True
            _write_from_parsed(dest, ir, parsed)
        except Exception as e:
            result["llm"] = {"ok": False, "error": str(e)[:400]}
            if not (dest / "原始文件分析.md").exists():
                (dest / "原始文件分析.md").write_text(
                    f"# 原始文件分析\n\nLLM 失败：{e}\n\n仍可读 [文件索引.md](文件索引.md)。\n",
                    encoding="utf-8",
                )
    else:
        (dest / "原始文件分析.md").write_text(
            "# 原始文件分析\n\n未配置 LLM_API_KEY（或 OPENAI_API_KEY / DEEPSEEK_API_KEY）。"
            "已列出文件索引，可稍后配置再跑。\n",
            encoding="utf-8",
        )

    ir["ai_analysis"] = result
    return result


def _ensure_raw_agents(job_dir: Path) -> None:
    raw = raw_dir(job_dir)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "AGENTS.md").write_text(
        "# AGENTS.md — raw\n\n"
        "这是解包后的原始数据。DSH 只读这里。\n\n"
        "- `unpacked/` APK 解开\n"
        "- `extract/normalized/` 抽出的配置/脚本/图音\n"
        "- `ir/` 机器索引\n\n"
        "不要读 apk/so/dex。把完整中文策划稿写到 `../output/策划/`。\n"
        "那是最终成品。写给人看的 GDD，不要类名、不要文件路径、不要「来源」。\n"
        "关卡按章写 markdown，不要输出空的 chXXX_lvYYY.json。\n"
        "PNG 已在 `../output/美术/`，用 markdown 图片引用。\n",
        encoding="utf-8",
    )


def _llm_pass(job_dir: Path, ir: dict, files: list[Path], cfg: LlmConfig) -> dict:
    from gameaihack.core.progress import log

    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    engine = (ir.get("fingerprint") or {}).get("engine") or "unknown"
    genre = (ir.get("genre_guess") or {}).get("id") or "未判定"
    batches = batch_text(job_dir, files)
    log(f"[llm] {cfg.model} @ {cfg.openai_base}  文件 {len(files)}，{len(batches)} 批")
    merged: dict = {}
    notes: list[str] = []
    n = min(len(batches), 4)
    for i, batch in enumerate(batches[:4], 1):
        user = USER_TMPL.format(
            pkg=pkg,
            engine=engine,
            genre=genre,
            n_lv=len(ir.get("levels") or []),
            n_tb=len(ir.get("tables") or []),
            n_res=len(ir.get("resources") or []),
            batch=batch,
        )
        if i > 1:
            user = f"这是第 {i} 批文件，请增量补充 JSON，字段同前。\n" + user
        log(f"[llm] 第 {i}/{n} 批，约 {len(batch)} 字 …")
        text = chat(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            cfg=cfg,
        )
        parsed = _coerce_json(text)
        log(f"[llm] 第 {i}/{n} 批完成，{'JSON' if parsed else '原文'} {len(text)} 字")
        notes.append(text if not parsed else "")
        if parsed:
            _merge_parsed(merged, parsed)
        else:
            merged.setdefault("gdd_markdown", "")
            merged["gdd_markdown"] += "\n\n" + text
    if not merged.get("summary") and notes:
        merged["summary"] = (ir.get("package") or {}).get("name") or ""
        merged["gdd_markdown"] = "\n\n".join(n for n in notes if n)
    return merged


def _write_from_parsed(dest: Path, ir: dict, parsed: dict) -> None:
    summary = parsed.get("summary") or ""
    lines = [
        f"# 原始文件分析\n",
        f"{summary}\n",
        f"品类（模型）：{parsed.get('genre') or '—'}  · 规则品类：{(ir.get('genre_guess') or {}).get('id') or '—'}\n",
        "## 系统\n",
    ]
    for s in parsed.get("systems") or []:
        if not isinstance(s, dict):
            lines.append(f"- {s}")
            continue
        path = s.get("path") or ""
        ev = f"  `{path}`" if path else ""
        lines.append(f"- **{s.get('name', '')}**{ev}：{s.get('detail', '')}")
    lines.append("\n## 关卡\n")
    lines.append(str(parsed.get("levels") or "未知") + "\n")
    lines.append("## 经济\n")
    lines.append(str(parsed.get("economy") or "未知") + "\n")
    unks = parsed.get("unknowns") or []
    if unks:
        lines.append("## 未知\n")
        for u in unks:
            lines.append(f"- {u}")
        lines.append("")
    (dest / "原始文件分析.md").write_text("\n".join(lines), encoding="utf-8")
    gdd = (parsed.get("gdd_markdown") or "").strip()
    if gdd:
        (dest / "gdd.md").write_text(gdd if gdd.startswith("#") else "# 策划摘录\n\n" + gdd, encoding="utf-8")
    if parsed.get("levels"):
        (dest / "关卡.md").write_text(f"# 关卡\n\n{parsed['levels']}\n", encoding="utf-8")
    if parsed.get("economy"):
        (dest / "经济.md").write_text(f"# 经济\n\n{parsed['economy']}\n", encoding="utf-8")
    claims = ir.setdefault("claims", [])
    if summary and not any(c.get("id") == "claim_ai_summary" for c in claims):
        claims.append(
            {
                "id": "claim_ai_summary",
                "dimension": 1,
                "severity": "hypothesis",
                "text": f"AI 读原始文件：{summary}",
                "confidence": "medium",
                "evidence": [{"path": "output/策划/ai/原始文件分析.md", "extractor": "llm", "locator": "summary"}],
            }
        )
    for u in unks[:12]:
        if u and u not in (ir.get("unknowns") or []):
            ir.setdefault("unknowns", []).append(str(u))


def _coerce_json(text: str) -> dict | None:
    raw = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if m:
        raw = m.group(1)
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _merge_parsed(dst: dict, src: dict) -> None:
    if src.get("summary") and (not dst.get("summary") or len(str(src["summary"])) > len(str(dst.get("summary") or ""))):
        dst["summary"] = src["summary"]
    if src.get("genre"):
        dst["genre"] = src["genre"]
    syss = list(dst.get("systems") or [])
    for s in src.get("systems") or []:
        syss.append(s)
    dst["systems"] = syss[:40]
    for k in ("levels", "economy", "gdd_markdown"):
        extra = src.get(k)
        if extra:
            prev = dst.get(k) or ""
            dst[k] = (prev + "\n\n" + str(extra)).strip() if prev and str(extra) not in str(prev) else str(extra)
    unks = list(dst.get("unknowns") or [])
    for u in src.get("unknowns") or []:
        if u not in unks:
            unks.append(u)
    dst["unknowns"] = unks[:40]
