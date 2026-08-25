"""读 raw/，经 grok / Codex / DSH 驱动写出 ../output/策划。"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from gameaihack.agent.corpus import batch_text, index_markdown, iter_source_files
from gameaihack.agent.drivers import AgentRequest, is_retryable, parse_via, resolve_driver
from gameaihack.agent.llm import LlmConfig, chat, resolve_llm
from gameaihack.core.layout import design_dir, raw_dir

SYSTEM = (
    "你是游戏策划。输入是从安装包解出来的原始文本。"
    "写给 TapTap Maker / Cindy 的制作说明书：在 Maker 工程里做出玩法相同的新游戏。"
    "读者打开的是 output/（Maker 目录：scripts/、assets/、策划/）。"
    "关卡表写「第几关 / 这一关干什么 / 通关后开哪」，不要写机器编号、Unity 路径、IR 字段。"
    "不要写「用自己的引擎」。不要写 Unity 类名、程序集、catalog、rebuild_grade、「来源：」。"
    "不要写盗版客户端、外挂、密钥。广告 SDK / Firebase 忽略。"
    "不要创建「已迁移」的重复文件。"
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

BOOK_PROMPT = """你写的不是分析备忘，而是一份**给 TapTap Maker 开工的制作说明书**。
读者用 Cindy 打开 output/（这就是 Maker 工程），对照 策划 + 美术 做出玩法相同的新游戏。
不要重打包原 APK。不要写「用自己的引擎」。

工程约定：
- 脚本 `scripts/main.lua`，2D 物理用 Box2D
- 上架图生成到 `assets/image/`；`美术/` 只对照，不要当商用素材
- 第一局必须小到能 `maker_build` 预览
- 制作顺序第 1 步是装 Maker MCP，第 2 步是本目录已是 init 后的工程（没有 `.project` 再 `npx -y @taptap/maker init`）
- Lua 不要用 os.clock / io.*

**事实源（最高优先级，先读完再写）：**
- `output/策划/_事实源.md`  机器把 raw 清单 + 美术清单合成的一份，必须遵守
- `output/美术/清单/给策划.md`  能用的美术目录和代表文件
- `raw/清单/给策划.md`  能写的表、关卡、引擎事实
- 详细表：`美术/清单/全部.csv`、`raw/ir/*.json`

禁止：
- 发明事实源里没有的美术目录或系统名
- 嵌图 path 不在美术清单里
- 把 IR 里的 merge/模板品类当成玩法（以 raw 文件和美术清单为准）
- 编造关卡坐标、Unity 类名、盗版客户端
- 关卡表用 `ch001_lv001`、原资源名、Unity 路径当主列
- 把只看到章名的章编成「原作关卡表」或每行写「占位关，非原作数量」
- 新建 03-关卡.md、04-数据表.md、05-大厅成长商店.md 这种「已迁移」重复文件
- 把 99 章写成同一段解包笔记复制 99 次

关卡怎么写：
- 人话：第几章第几关、这一关干什么、通关后开哪一关
- 同一章很多关且信息相同，合并成「第 3～14 关」一行
- 只看到章名时写「本章关数未知」，重做建议另表，标明是建议不是原作
- 分章正文由机器生成，你不要覆盖成机器编号表

完成标准：
- Cindy 只看 02-核心玩法 + 制作顺序 能在 Maker 里做第一局并预览
- 图鉴文件夹与美术清单一一对应
- 06-系统总表：系统 | 依据（人话，不要类名）| 美术清单目录 | 代表图
- 整局过程写全：大厅 → 开局 → 操作 → 胜负 → 结算 → 成长/商店
- 没证据标「未知，重做时自行设计」
"""


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


def _ir_brief(ir: dict) -> str:
    fp = ir.get("fingerprint") or {}
    genre = (ir.get("genre_guess") or {}).get("id") or "未判定"
    n_lv = len(ir.get("levels") or [])
    n_tb = len(ir.get("tables") or [])
    n_res = len(ir.get("resources") or [])
    claims = ir.get("claims") or []
    bits = []
    for c in claims[:12]:
        t = str(c.get("text") or "").strip()
        if t:
            bits.append(f"- {t}")
    claim_txt = "\n".join(bits) or "- （IR 尚无主张）"
    return (
        f"引擎 {fp.get('engine') or '—'} / {fp.get('script_backend') or '—'}，"
        f"品类猜测 {genre}，关卡 {n_lv}，表 {n_tb}，资源 {n_res}。\n\n"
        f"机器已抽出的主张（供核对，以 raw 为准）：\n{claim_txt}\n"
    )


def book_tasks(job_dir: Path, ir: dict) -> list[tuple[str, str]]:
    """分步还原整包：核心玩法 → 系统全书 → 关卡+图鉴。"""
    from gameaihack.content.facts import load_fact_source, write_fact_source

    pkg = (ir.get("package") or {}).get("name") or job_dir.name
    n_lv = len(ir.get("levels") or [])
    chapters = _chapter_list(ir)
    n_ch = len(chapters) or 0
    facts = load_fact_source(job_dir)
    if not facts.strip():
        write_fact_source(job_dir, ir)
        facts = load_fact_source(job_dir)
    if len(facts) > 12000:
        facts = facts[:12000] + "\n\n（事实源过长，已截断。完整见 output/策划/_事实源.md）\n"
    head = (
        BOOK_PROMPT
        + f"\n游戏 `{pkg}`。\n"
        + _ir_brief(ir)
        + "\n## 事实源摘录（完整文件在 策划/_事实源.md）\n\n"
        + facts
        + "\n\n先读 `output/策划/_事实源.md`，再读 raw/ir/ 与 美术/清单/。不要 ls 上万张 PNG。\n"
    )
    return [
        (
            "核心玩法",
            head
            + "写制作入口和能直接做出来的第一局。文件：\n"
            + "- 策划/README.md：制作入口。先做什么、读哪几篇、美术怎么用\n"
            + "- 策划/制作顺序.md：从装 Maker MCP、本目录 init，到第一局可预览（建议 8～15 步）\n"
            + "- 策划/00-封面.md：这是什么游戏、谁玩、一句话循环、对照图\n"
            + "- 策划/01-产品定位.md：品类、对标、留存（有证据才写）\n"
            + "- 策划/02-核心玩法.md 必须按下面小标题写全，写到能做一局：\n"
            + "  1. 玩家目标  2. 一局时间线（从点开始到结算，逐步）\n"
            + "  3. 操作与输入  4. 场上有什么（角色/道具/障碍）\n"
            + "  5. 胜负与失败  6. 计分/星级/评价  7. HUD 与关键界面\n"
            + "  8. 大厅如何进这一局  9. 重做时第一周只做哪些\n"
            + "封面和 02 的嵌图必须来自事实源「代表文件」。图鉴目录名不要自己起。写完列出文件。\n",
        ),
        (
            "系统全书",
            head
            + "把整包系统写成制作规格，别人按文档就能做功能列表。全文用人话：\n"
            + "- 03-关卡设计.md：关卡是什么、怎么解锁、一关怎么配\n"
            + "- 04-成长与进度.md：账号存什么、换装/赛季外壳、哪一周才加成长\n"
            + "- 05-经济与商业化.md：货币图标、商店皮、广告/付费点；没有价格就写没有，不要把资源清单写成价目\n"
            + "- 06-系统总表.md：系统 | 依据（人话）| 美术目录 | 代表图 | 入口 | 第一局做不做\n"
            + "- 07-新手-UI-社交.md：屏幕流（启动→大厅→冒险→结算）、按钮、社交\n"
            + "- 08-技术约束.md：横屏、Maker 2D 物理（Box2D）、资源放 assets/。不要写 IR 字段名\n"
            + "- 09-未知与下一步.md：必须自补的清单，用人话，不要程序集名当表头\n"
            + "不要写 Unity 类名、程序集、IR 字段、catalog、table:xxx 当主列。\n"
            + "06 的「美术目录」必须填事实源里的文件夹名。没证据写未知。\n",
        ),
        (
            "关卡与图鉴",
            head
            + f"美术必须能直接拿去对照。包里大约 {n_ch or '若干'} 章（索引 {n_lv} 条，不是已经解出的关卡图）。\n"
            + "- 不要写 关卡/第001章.md 这些分章正文（机器会生成人话关卡表：第几关 / 干什么 / 通关开哪）\n"
            + "- 关卡/README.md 只写先做哪一章；不要写成解包索引，不要出现「原资源名」\n"
            + "- 图鉴/README.md 已按事实源建好目录，补全「用在哪」\n"
            + "- 事实源里每个美术文件夹一篇 图鉴/<文件夹名>.md，文件名必须一致\n"
            + "- 每篇用事实源列出的代表文件嵌图，写清在 Maker 里生成到 assets/image 后贴到哪\n"
            + "不要空 JSON，不要新增事实源没有的图鉴篇名。写完列出文件数量。\n",
        ),
    ]


dsh_book_tasks = book_tasks


def _retry_delays() -> list[float]:
    raw = os.environ.get("GAMEAIHACK_LLM_RETRY", "15,30,60")
    text = (raw or "").strip().lower()
    if text in {"0", "off", "none", ""}:
        return []
    out: list[float] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(max(0.0, float(part)))
        except ValueError:
            continue
    return out


def _run_driver(driver, req: AgentRequest, *, cfg=None) -> dict:
    delays = _retry_delays()
    last: dict = {"ok": False, "via": getattr(driver, "via", ""), "error": "未知错误"}
    attempts = 1 + len(delays)
    from gameaihack.core.progress import log

    for i in range(attempts):
        last = driver.run(req, cfg=cfg)
        if last.get("ok"):
            return last
        err = str(last.get("error") or "")
        if i >= attempts - 1 or not is_retryable(err):
            return last
        wait = delays[i]
        log(f"[{driver.via}] 并发/限额，{int(wait)}s 后重试（{i + 1}/{attempts}）：{err[:160]}")
        if wait:
            time.sleep(wait)
    return last


def run_book(job_dir: Path, ir: dict, cfg: LlmConfig | None, *, via: str = "sdk") -> dict:
    """读 raw/ + 美术清单，写出策划。过程只打控制台（与 grok/codex CLI 同类）。"""
    from gameaihack.core.progress import log, stream

    via = parse_via(via)
    driver = resolve_driver(via)
    driver.require(cfg)
    dest = design_dir(job_dir)
    dest.mkdir(parents=True, exist_ok=True)
    stale = dest / "过程.md"
    if stale.is_file():
        try:
            stale.unlink()
        except OSError:
            pass
    tasks = book_tasks(job_dir, ir)
    results: list[dict] = []
    all_ok = True
    effort = (os.environ.get("GAMEAIHACK_EFFORT") or "xhigh").strip() or "xhigh"
    try:
        for i, (title, prompt) in enumerate(tasks, 1):
            stream(f"\n{via}  {i}/{len(tasks)}  {title}")
            req = AgentRequest(
                job_dir=job_dir,
                prompt=prompt,
                model=(cfg.model if cfg else "") or os.environ.get("LLM_MODELS") or "grok-4.6",
                timeout=int(os.environ.get("GAMEAIHACK_AGENT_TIMEOUT") or "3600"),
                effort=effort,
                api_key=cfg.api_key if cfg else "",
                base_url=cfg.base_url if cfg else "",
            )
            step = _run_driver(driver, req, cfg=cfg)
            results.append({"title": title, "ok": step.get("ok"), "error": step.get("error")})
            if step.get("ok"):
                stream(f"{via}  {title}  done")
            else:
                all_ok = False
                log(f"[{via}] 失败：{step.get('error') or 'unknown'}")
                break
    finally:
        closer = getattr(driver, "close", None)
        if callable(closer):
            closer()
    err = next((r.get("error") for r in results if not r.get("ok")), "")
    return {"ok": all_ok, "via": via, "error": err or "", "steps": results}


def run_dsh_book(job_dir: Path, ir: dict, cfg: LlmConfig) -> dict:
    """兼容旧名：走 dsh 通道。"""
    return run_book(job_dir, ir, cfg, via="dsh")


def run_ai_analysis(
    job_dir: Path,
    ir: dict,
    *,
    cfg: LlmConfig | None = None,
    via: str = "sdk",
) -> dict:
    """写入 策划/ai/，并把摘要挂到 ir['ai_analysis']。"""
    pytest_run = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if cfg is None and not pytest_run:
        cfg = resolve_llm()
    dest = design_dir(job_dir) / "ai"
    dest.mkdir(parents=True, exist_ok=True)
    files = iter_source_files(job_dir)
    (dest / "文件索引.md").write_text(index_markdown(job_dir, files), encoding="utf-8")
    result: dict = {
        "files": len(files),
        "via": via,
        "dsh": None,
        "agent": None,
        "llm": None,
        "ok": False,
    }
    if not files:
        (dest / "原始文件分析.md").write_text("# 原始文件分析\n\n没有可送进模型的文本文件。\n", encoding="utf-8")
        if pytest_run:
            ir["ai_analysis"] = result
            return result

    _ensure_raw_agents(job_dir)

    if not pytest_run:
        from gameaihack.core.progress import log

        log(f"[{via}] 准备读 raw/ 和 output/美术/，索引文件 {len(files)} 个")
        from gameaihack.content.accept import accept_design, snapshot_protected

        snap = snapshot_protected(job_dir)
        book = run_book(job_dir, ir, cfg, via=via)
        result["agent"] = {
            "ok": book.get("ok"),
            "via": book.get("via"),
            "error": book.get("error"),
            "steps": book.get("steps"),
        }
        if book.get("ok"):
            gaps = accept_design(job_dir, snap)
            if gaps:
                err = "策划未达到交差线：\n" + "\n".join(f"- {x}" for x in gaps)
                result["agent"]["ok"] = False
                result["agent"]["error"] = err
                book = result["agent"]
                log(f"[{via}] {err}")
        result["dsh"] = result["agent"]
        if book.get("ok"):
            result["ok"] = True
        elif book.get("error"):
            (dest / "agent.error.txt").write_text(str(book["error"]), encoding="utf-8")
        ir["ai_analysis"] = result
        return result

    if cfg and not result.get("ok"):
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
    elif not result.get("ok"):
        (dest / "原始文件分析.md").write_text(
            "# 原始文件分析\n\n未配置 LLM_API_KEY（或 OPENAI_API_KEY / DEEPSEEK_API_KEY）。"
            "已列出文件索引，可稍后配置再跑。\n",
            encoding="utf-8",
        )

    ir["ai_analysis"] = result
    return result


def _ensure_raw_agents(job_dir: Path) -> None:
    job_dir = Path(job_dir)
    (job_dir / "AGENTS.md").write_text(
        "# AGENTS.md\n\n"
        "任务：按 **事实源** 写制作说明书。\n\n"
        "- 先读 `output/策划/_事实源.md`（raw 清单 + 美术清单）\n"
        "- 只读 `raw/` 和 `output/美术/`。不要改 raw/ 和 `_事实源.md`\n"
        "- 图鉴目录名 = 美术清单文件夹；嵌图 path 必须在清单里\n"
        "- 系统必须对得上 raw 清单的表/关卡，对不上就写未知\n"
        "- `02-核心玩法.md` 要能在 TapTap Maker 做出第一局；`制作顺序.md` 从 MCP / init 写起\n"
        "- 关卡表写第几关、干什么、通关开哪。不要写机器编号当主列，不要写 Unity 路径\n"
        "- 不要写「用自己的引擎」。读者打开的是 output/ 这个 Maker 工程\n"
        "- 不要新建「已迁移」的重复文件\n",
        encoding="utf-8",
    )
    raw = raw_dir(job_dir)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "AGENTS.md").write_text(
        "# AGENTS.md — raw\n\n"
        "这是解包后的原始数据。模型只读这里。\n\n"
        "- `unpacked/` APK 解开\n"
        "- `extract/normalized/` 抽出的配置/脚本/图音\n"
        "- `ir/` 机器索引\n\n"
        "不要读 apk/so/dex。把**可制作新游戏**的中文说明书写到 `../output/策划/`。\n"
        "还原整局过程与全部能还原的系统。不要类名、不要编造坐标。\n"
        "PNG 在 `../output/美术/`，用 markdown 引用。\n",
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
