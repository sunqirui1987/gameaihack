from __future__ import annotations

import re
from pathlib import Path

from gameaihack.core.paths import load_yaml

AD_PAT = re.compile(
    r"ShowRewardVideo|RewardedAd|rewarded_video|UnityAds|AppLovin|IronSource|AdMob|激励视频",
    re.I,
)
IAP_PAT = re.compile(
    r"BillingClient|SkuDetails|\bIAP\b|InAppPurchase|productId|product_id|内购",
    re.I,
)
STAMINA_PAT = re.compile(r"stamina|energy|体力|精力", re.I)
GACHA_PAT = re.compile(r"gacha|recruit|wish|抽卡|十连|pity", re.I)
TRACK_PAT = re.compile(
    r"""(?:Track|LogEvent|logEvent|Report)\(\s*['"]([A-Za-z0-9_./]+)['"]""",
)
SHAKE_PAT = re.compile(r"CameraShake|HitStop|coyote|jumpBuffer|Vibrate|Juice", re.I)
NET_PAT = re.compile(r"https?://|/api/|protobuf|HttpClient|WWW\.|UnityWebRequest", re.I)


def scan_text_blob(merged: Path, norm: Path, limit_files: int = 400) -> str:
    from gameaihack.core.fs import iter_files

    chunks: list[str] = []
    n = 0
    text_suf = {".lua", ".js", ".json", ".txt", ".xml", ".cs", ".gd", ".tscn", ".csv", ".plist"}
    for root in (norm, merged):
        if not root.exists():
            continue
        for p in iter_files(root):
            if p.suffix.lower() not in text_suf:
                continue
            try:
                if p.stat().st_size > 1_500_000:
                    continue
                chunks.append(p.read_text(encoding="utf-8", errors="ignore")[:80000])
            except OSError:
                continue
            n += 1
            if n >= limit_files:
                return "\n".join(chunks)
    return "\n".join(chunks)


def collect_claims(ir: dict, blob: str) -> list[dict]:
    claims: list[dict] = []
    fp = ir.get("fingerprint") or {}
    pkg = ir.get("package") or {}

    def add(cid, dim, text, evidence, *, confidence="high", severity="confirmed"):
        ev = evidence if isinstance(evidence, list) else [evidence]
        if severity == "confirmed" and not ev:
            severity = "hypothesis"
            confidence = "hypothesis"
        claims.append(
            {
                "id": cid,
                "dimension": dim,
                "severity": severity,
                "text": text,
                "confidence": confidence,
                "evidence": ev,
            }
        )

    add(
        "claim_identity_engine",
        1,
        f"引擎判定为 {fp.get('engine')} / {fp.get('script_backend') or 'n/a'}（规则 {', '.join(fp.get('matched_rules') or []) or '无'}）",
        [{"path": "fingerprint.json", "extractor": "fingerprint", "locator": "engine"}],
    )
    if pkg.get("name") and pkg["name"] != "unknown.pack":
        add("claim_identity_pkg", 1, f"包名 {pkg['name']}", [{"path": "AndroidManifest", "extractor": "ingest", "locator": pkg["name"]}])

    genre = ir.get("genre_guess") or {}
    if genre.get("id"):
        add(
            "claim_genre",
            1,
            f"品类启发式：{genre['id']}（置信 {genre.get('confidence')}）",
            [{"path": "ir/genre", "extractor": "genre", "locator": genre["id"]}],
            confidence="medium",
        )

    n_tex = sum(1 for r in ir.get("resources") or [] if r.get("kind") in {"texture", "sprite"})
    n_aud = sum(1 for r in ir.get("resources") or [] if r.get("kind") == "audio")
    if n_tex:
        add("claim_art", 2, f"抽出纹理/精灵 {n_tex} 个", [{"path": "extract/normalized/textures", "extractor": "loose", "locator": "count"}])
    if n_aud:
        add("claim_audio", 2, f"抽出音频 {n_aud} 个", [{"path": "extract/normalized/audio", "extractor": "loose", "locator": "count"}])

    if AD_PAT.search(blob):
        m = AD_PAT.search(blob)
        add("claim_ads", 11, f"存在激励/插屏广告点（命中 `{m.group(0)}`）", [{"path": "scripts", "extractor": "design.ads", "locator": m.group(0)}])
        ir.setdefault("monetization", {}).setdefault("ads", []).append({"id": m.group(0), "evidence": "script"})
    if IAP_PAT.search(blob):
        m = IAP_PAT.search(blob)
        add("claim_iap", 11, f"存在 IAP/支付相关代码或字段（命中 `{m.group(0)}`）", [{"path": "scripts", "extractor": "design.iap", "locator": m.group(0)}])
        ir.setdefault("monetization", {}).setdefault("iap", []).append({"id": m.group(0)})

    stamina_tables = [t for t in ir.get("tables") or [] if t.get("role") == "economy_const" or any("stamina" in c["name"].lower() or "energy" in c["name"].lower() for c in t.get("columns") or [])]
    if STAMINA_PAT.search(blob) or stamina_tables:
        loc = stamina_tables[0]["id"] if stamina_tables else "script"
        add("claim_stamina", 10, "存在体力/精力类资源", [{"path": loc, "extractor": "design.stamina", "locator": "stamina|energy"}])

    if GACHA_PAT.search(blob) or any(t.get("role") == "gacha" for t in ir.get("tables") or []):
        add("claim_gacha", 11, "存在抽卡/招募相关痕迹", [{"path": "tables_or_script", "extractor": "design.gacha", "locator": "gacha"}])

    shop_tables = [t for t in ir.get("tables") or [] if t.get("role") in {"shop", "iap"}]
    if shop_tables:
        add("claim_shop", 10, f"商店/价格表 {len(shop_tables)} 张", shop_tables[0].get("evidence") or [{"path": shop_tables[0]["id"], "extractor": "tables", "locator": "role=shop"}])
    iap_tables = [t for t in ir.get("tables") or [] if t.get("role") == "iap"]
    if iap_tables and not any(c["id"] == "claim_iap" for c in claims):
        add(
            "claim_iap",
            11,
            f"IAP/sku 表 {iap_tables[0]['id']}",
            iap_tables[0].get("evidence") or [{"path": iap_tables[0]["id"], "extractor": "tables", "locator": "role=iap"}],
        )

    currencies = _currencies(ir)
    if currencies:
        ir["economy"]["currencies"] = [{"id": c} for c in currencies]
        add("claim_currency", 10, "货币：" + ", ".join(currencies), [{"path": "tables", "extractor": "design.economy", "locator": ",".join(currencies)}])

    levels = ir.get("levels") or []
    if levels:
        l2 = sum(1 for lv in levels if str(lv.get("rebuild_grade", "L0")) >= "L2")
        add("claim_levels", 6, f"关卡索引 {len(levels)}，其中布局可达 L2+：{l2}", [{"path": "ir/levels", "extractor": "levels", "locator": "count"}])
        if any(lv.get("win") or lv.get("lose") for lv in levels):
            add("claim_rules", 7, "至少部分关卡含胜负条件", [{"path": "ir/levels", "extractor": "levels", "locator": "win/lose"}])

    enemies = [t for t in ir.get("tables") or [] if t.get("role") == "enemy"]
    if enemies:
        add("claim_combat", 8, f"敌人数值表 {enemies[0]['id']}（{enemies[0]['row_count']} 行）", enemies[0].get("evidence") or [{"path": enemies[0]["id"], "extractor": "tables", "locator": "enemy"}])
        ir.setdefault("entity_templates", [])
        for row in (enemies[0].get("preview_rows") or [])[:30]:
            eid = str(row.get("id") or row.get("name") or len(ir["entity_templates"]))
            ir["entity_templates"].append(
                {
                    "id": f"entity:{eid}",
                    "display_name": str(row.get("name") or eid),
                    "role": "enemy",
                    "stats": {k: row.get(k) for k in row if k.lower() in {"hp", "atk", "attack", "def", "defense", "speed"}},
                    "source_table": enemies[0]["id"],
                    "evidence": enemies[0].get("evidence") or [],
                }
            )

    events = TRACK_PAT.findall(blob)
    if events:
        uniq = sorted(set(events))[:80]
        ir["analytics_events"] = [{"name": e} for e in uniq]
        add("claim_analytics", 19, f"埋点事件 {len(uniq)} 个（如 {', '.join(uniq[:5])}）", [{"path": "scripts", "extractor": "design.track", "locator": uniq[0]}])

    juice = SHAKE_PAT.findall(blob)
    if juice:
        ir["feel"]["juice"] = [{"id": j} for j in sorted(set(juice))]
        add("claim_juice", 18, "手感/Juice 符号：" + ", ".join(sorted(set(juice))[:8]), [{"path": "scripts", "extractor": "design.feel", "locator": juice[0]}])

    if ir.get("verbs"):
        add(
            "claim_verbs",
            4,
            "玩家动词：" + ", ".join(v["id"] for v in ir["verbs"][:12]),
            [{"path": "scripts", "extractor": "design.verbs", "locator": ir["verbs"][0]["id"]}],
        )

    loc = ir.get("loc") or {}
    if loc.get("samples"):
        langs = ",".join(loc.get("languages") or []) or "und"
        add(
            "claim_loc",
            13,
            f"文案抽样 {len(loc['samples'])} 条，语言 {langs}",
            [{"path": "loc", "extractor": "loc", "locator": langs}],
        )

    teaching = []
    for lv in (ir.get("levels") or [])[:3]:
        teaching.extend(lv.get("teaching") or [])
    if teaching:
        add(
            "claim_ftue",
            14,
            "前三关新机制：" + ", ".join(str(x) for x in teaching[:12]),
            [{"path": "ir/levels", "extractor": "levels.teaching", "locator": "first3"}],
        )

    if NET_PAT.search(blob):
        add("claim_net", 17, "客户端含网络请求痕迹；部分规则可能在服务端", [{"path": "scripts", "extractor": "design.net", "locator": "http"}], confidence="medium")
        ir["network"]["apis"].append({"id": "http", "note": "script_match"})

    if levels and all(lv.get("rebuild_grade") == "L0" for lv in levels) and any(t.get("role") == "level" for t in ir.get("tables") or []):
        add(
            "claim_server_levels",
            17,
            "有关卡表但无可画出的布局，倾向关卡在服务端或私有二进制",
            [{"path": "ir/levels", "extractor": "design.network", "locator": "L0"}],
            confidence="medium",
        )
        ir["network"]["server_authoritative"].append("levels")

    if fp.get("hotupdate"):
        add("claim_hotupdate", 20, "热更形态：" + ", ".join(fp["hotupdate"]), [{"path": "fingerprint", "extractor": "fingerprint", "locator": "hotupdate"}])
    if fp.get("protection"):
        add("claim_protect", 20, "保护：" + ", ".join(fp["protection"]), [{"path": "fingerprint", "extractor": "fingerprint", "locator": "protection"}])

    _fill_loops(ir, genre.get("id"), claims)
    return claims


def _currencies(ir: dict) -> list[str]:
    names = []
    for t in ir.get("tables") or []:
        for c in t.get("columns") or []:
            n = c["name"].lower()
            if n in {"gold", "coin", "diamond", "gem", "stamina", "energy", "cash", "ticket"}:
                if n not in names:
                    names.append(n)
    return names


def _fill_loops(ir: dict, genre: str | None, claims: list[dict]) -> None:
    session = []
    if genre == "puzzle":
        session = [{"id": "start"}, {"id": "board"}, {"id": "settle"}, {"id": "next"}]
    elif genre == "rpg":
        session = [{"id": "map"}, {"id": "battle"}, {"id": "reward"}, {"id": "map"}]
    elif genre == "td":
        session = [{"id": "build"}, {"id": "wave"}, {"id": "settle"}]
    elif genre == "merge":
        session = [{"id": "merge"}, {"id": "spawn"}, {"id": "collect"}]
    elif ir.get("levels"):
        session = [{"id": "enter_level"}, {"id": "play"}, {"id": "result"}]
    day = []
    if any(c["id"] == "claim_stamina" for c in claims):
        day = [{"id": "login"}, {"id": "spend_stamina"}, {"id": "regen"}]
    meta = []
    if any(c["id"] == "claim_gacha" for c in claims):
        meta.append({"id": "gacha"})
    if any(c["id"] == "claim_iap" for c in claims):
        meta.append({"id": "iap"})
    ir["loops"] = {"session": session, "day": day, "meta": meta}
    if session:
        claims.append(
            {
                "id": "claim_loop",
                "dimension": 1,
                "severity": "hypothesis" if not genre else "confirmed",
                "text": "局内循环：" + " → ".join(x["id"] for x in session),
                "confidence": "medium" if genre else "low",
                "evidence": [{"path": "genre", "extractor": "design.loop", "locator": genre or "levels"}] if genre or ir.get("levels") else [],
            }
        )
        if claims[-1]["severity"] == "confirmed" and not claims[-1]["evidence"]:
            claims[-1]["severity"] = "hypothesis"

    sources, sinks = [], []
    if any(c["id"] == "claim_ads" for c in claims):
        sources.append("rewarded_ad")
    if any(c["id"] == "claim_iap" for c in claims):
        sources.append("iap")
    if ir.get("levels"):
        sources.append("level_reward")
        sinks.append("continue_level")
    if any(c["id"] == "claim_stamina" for c in claims):
        sinks.append("stamina")
        sources.append("stamina_regen")
    ir["economy"]["sources"] = [{"id": s} for s in sources]
    ir["economy"]["sinks"] = [{"id": s} for s in sinks]
    ir["economy"]["edges"] = [{"from": a, "to": b} for a, b in zip(sources, sinks)] if sources and sinks else []


def score_radar(ir: dict) -> list[dict]:
    dims = load_yaml("radar_dimensions.yaml")["dimensions"]
    claims = ir.get("claims") or []
    by_dim: dict[int, list] = {}
    for c in claims:
        by_dim.setdefault(int(c.get("dimension") or 0), []).append(c)

    def ev_count(n: int) -> int:
        return sum(len(c.get("evidence") or []) for c in by_dim.get(n, []))

    def has(cid: str) -> bool:
        return any(c["id"] == cid for c in claims)

    n_res = len(ir.get("resources") or [])
    n_tab = len(ir.get("tables") or [])
    n_lv = len(ir.get("levels") or [])
    l2 = sum(1 for lv in ir.get("levels") or [] if str(lv.get("rebuild_grade", "L0")) >= "L2")
    engine = (ir.get("fingerprint") or {}).get("engine")
    pkg = (ir.get("package") or {}).get("name")

    scores = {
        "identity": 3 if engine and engine != "unknown" else 1,
        "presentation": 1 if n_res else 0,
        "feel": 2 if ir.get("feel", {}).get("juice") else 0,
        "verbs": 3 if has("claim_verbs") else (2 if (ir.get("verbs") or n_lv or has("claim_loop")) else 0),
        "content": min(5, 1 + n_tab),
        "levels": 0,
        "rules": 2 if has("claim_rules") else 0,
        "combat": 3 if has("claim_combat") else 0,
        "progression": 2 if any((lv.get("unlock") or {}).get("requires") for lv in ir.get("levels") or []) else 0,
        "economy": 3 if has("claim_currency") or has("claim_shop") else (2 if has("claim_stamina") else 0),
        "monetization": 0,
        "social": 1 if re.search(r"guild|friend|clan|公会|好友", str(ir.get("analytics_events"))) else 0,
        "narrative": 3 if has("claim_loc") else (2 if any(t.get("role") == "dialogue" for t in ir.get("tables") or []) else 0),
        "ftue": 3 if has("claim_ftue") else (2 if any("guide" in str(lv.get("id")).lower() or "tutorial" in str(lv.get("id")).lower() for lv in ir.get("levels") or []) else 0),
        "ux": 2 if ir.get("ui", {}).get("screens") else 0,
        "liveops": 2 if any(t.get("role") in {"quest"} and "event" in t.get("id", "") for t in ir.get("tables") or []) else 0,
        "network": 3 if has("claim_server_levels") or has("claim_net") else 1,
        "juice": 3 if has("claim_juice") else 0,
        "analytics": 3 if has("claim_analytics") else 0,
        "tech": 2 if engine and engine != "unknown" else 0,
    }
    if pkg and pkg != "unknown.pack":
        scores["identity"] = max(scores["identity"], 2)
    if ir.get("genre_guess", {}).get("id"):
        scores["identity"] = max(scores["identity"], 4)
    if n_res >= 5:
        scores["presentation"] = 3
    if n_res >= 20:
        scores["presentation"] = 4
    if n_lv:
        scores["levels"] = 2
    if l2:
        scores["levels"] = 4
    if l2 and has("claim_rules"):
        scores["levels"] = 5
    if has("claim_ads") or has("claim_iap") or has("claim_gacha"):
        scores["monetization"] = 4 if (has("claim_ads") and has("claim_iap")) else 3
    if (ir.get("fingerprint") or {}).get("hotupdate"):
        scores["tech"] = max(scores["tech"], 3)
    if (ir.get("fingerprint") or {}).get("protection"):
        scores["tech"] = max(scores["tech"], 3)

    items = []
    id_to_num = {d["id"]: i + 1 for i, d in enumerate(dims)}
    for d in dims:
        did = d["id"]
        score = int(max(0, min(5, scores.get(did, 0))))
        n = id_to_num[did]
        blockers = []
        if score == 0:
            blockers.append("no_signal")
        if did == "levels" and n_lv and not l2:
            blockers.append("layout_not_decoded")
        if did == "combat" and score < 3:
            blockers.append("formula_unknown")
        items.append(
            {
                "dimension": did,
                "label": d.get("label") or did,
                "score": score,
                "max": 5,
                "evidence_count": ev_count(n),
                "blockers": blockers,
                "mode_needed_to_improve": "deep" if did in {"feel", "combat", "network"} and score < 3 else "standard",
            }
        )
    return items


def simulate(ir: dict) -> list[dict]:
    out = []
    enemies = [t for t in ir.get("entity_templates") or [] if t.get("role") == "enemy"]
    if enemies:
        hps = []
        atks = []
        for e in enemies:
            st = e.get("stats") or {}
            for k, v in st.items():
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if k.lower() == "hp":
                    hps.append(fv)
                if k.lower() in {"atk", "attack"}:
                    atks.append(fv)
        if hps:
            player_dps = (atks[0] if atks else 10) * 0.8
            t = (sum(hps) / max(len(hps), 1)) / max(player_dps, 0.01)
            note = "ok"
            if t < 0.5 or t > 3600:
                note = "implausible"
            out.append(
                {
                    "kind": "combat",
                    "avg_hp": round(sum(hps) / len(hps), 2),
                    "est_clear_sec": round(t, 2),
                    "note": note,
                }
            )
    if any(c.get("id") == "claim_stamina" for c in ir.get("claims") or []):
        out.append(
            {
                "kind": "economy",
                "days": 7,
                "note": "未还原回复公式，仅标记存在体力墙风险",
            }
        )
    return out


def mermaid_flow(nodes: list[dict], title: str) -> str:
    if not nodes:
        return f"%% {title} empty\n"
    ids = [n["id"] for n in nodes]
    lines = [f"flowchart LR", f"  %% {title}"]
    for a, b in zip(ids, ids[1:]):
        lines.append(f"  {a} --> {b}")
    if len(ids) == 1:
        lines.append(f"  {ids[0]}")
    return "\n".join(lines) + "\n"


def mermaid_economy(ir: dict) -> str:
    src = [x["id"] for x in ir.get("economy", {}).get("sources") or []]
    snk = [x["id"] for x in ir.get("economy", {}).get("sinks") or []]
    cur = [x["id"] for x in ir.get("economy", {}).get("currencies") or []]
    if not (src or snk or cur):
        return "%% economy empty\n"
    lines = ["flowchart LR"]
    for s in src:
        lines.append(f"  {s} --> wallet")
    for c in cur:
        lines.append(f"  wallet --> {c}")
    for k in snk:
        lines.append(f"  wallet --> {k}")
    return "\n".join(lines) + "\n"


DIM_CHAPTER = {
    1: "01-身份证与循环.md",
    2: "01-身份证与循环.md",
    3: "02-操作系统与手感.md",
    4: "02-操作系统与手感.md",
    5: "03-内容库.md",
    6: "04-关卡设计.md",
    7: "04-关卡设计.md",
    8: "05-数值与公式.md",
    9: "05-数值与公式.md",
    10: "06-经济与商业化.md",
    11: "06-经济与商业化.md",
    12: "07-新手-UI-运营.md",
    13: "07-新手-UI-运营.md",
    14: "07-新手-UI-运营.md",
    15: "07-新手-UI-运营.md",
    16: "07-新手-UI-运营.md",
    17: "08-客户端服务器与技术.md",
    18: "02-操作系统与手感.md",
    19: "08-客户端服务器与技术.md",
    20: "08-客户端服务器与技术.md",
}


def render_gdd_chapters(ir: dict) -> dict[str, str]:
    grouped: dict[str, list] = {}
    for c in ir.get("claims") or []:
        fn = DIM_CHAPTER.get(int(c.get("dimension") or 0), "09-未知项.md")
        grouped.setdefault(fn, []).append(c)
    out: dict[str, str] = {}
    titles = {
        "01-身份证与循环.md": "身份证与循环",
        "02-操作系统与手感.md": "操作系统与手感",
        "03-内容库.md": "内容库",
        "04-关卡设计.md": "关卡设计",
        "05-数值与公式.md": "数值与公式",
        "06-经济与商业化.md": "经济与商业化",
        "07-新手-UI-运营.md": "新手 / UI / 运营",
        "08-客户端服务器与技术.md": "客户端 / 服务器 / 技术",
    }
    for fn, title in titles.items():
        lines = [f"# {title}\n"]
        items = grouped.get(fn) or []
        if not items:
            lines.append("本章无已确认主张。见未知项。\n")
        for c in items:
            lines.append(f"## {c['id']} · {c.get('severity')} / {c.get('confidence')}\n")
            lines.append(c["text"] + "\n")
            if c.get("evidence"):
                lines.append("证据：")
                for e in c["evidence"]:
                    lines.append(f"- `{e.get('path')}` · {e.get('extractor')} · {e.get('locator')}")
                lines.append("")
        out[fn] = "\n".join(lines)
    return out
