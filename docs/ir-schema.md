# GameIR Schema

GameIR 是引擎无关的分析中间层。所有 adapter 的目标都是填充它；关卡重建与策划合成只读它。

编码：UTF-8 JSON。  
校验：`gameaihack ir-validate`。  
原则：可追加字段，但不得删除下列必填字段；未知用 `null` + `unknowns`，禁止编造。

---

## 1. 顶层 `game.ir.json`

```json
{
  "$schema": "gameaihack.gameir.v1",
  "job_id": "20260824-foo",
  "package": {
    "name": "com.example.game",
    "version_name": "1.2.3",
    "version_code": 123,
    "sha256": "...",
    "min_sdk": 24,
    "orientation": "portrait"
  },
  "input_profile": {
    "files": [{"kind": "xapk", "sha256": "...", "bytes": 0}],
    "score": 42,
    "warnings": ["likely_shell_missing_obb"]
  },
  "fingerprint": { },
  "genre_guess": {"id": "merge", "confidence": 0.6},
  "resources": [],
  "entity_templates": [],
  "tables": [],
  "levels": [],
  "ui": { "screens": [], "flows": [] },
  "loc": { "languages": ["zh-CN"], "samples": [] },
  "verbs": [],
  "loops": { "session": [], "day": [], "meta": [] },
  "economy": { "currencies": [], "sources": [], "sinks": [], "edges": [] },
  "progression": { "nodes": [], "edges": [] },
  "monetization": { "iap": [], "ads": [], "gacha": [] },
  "feel": { "input": [], "camera": [], "juice": [] },
  "formulas": [],
  "analytics_events": [],
  "network": { "client_authoritative": [], "server_authoritative": [], "apis": [] },
  "claims": [],
  "radar": [],
  "simulations": [],
  "unknowns": [],
  "coverage": { }
}
```

---

## 2. Fingerprint

```json
{
  "engine": "unity",
  "engine_version": "2022.3.x",
  "script_backend": "il2cpp",
  "hotupdate": ["addressables", "hybridclr"],
  "protection": ["none"],
  "splits": ["base", "unity", "arm64"],
  "has_obb": false,
  "signals": [
    {"path": "lib/arm64-v8a/libil2cpp.so", "rule": "unity_il2cpp"}
  ],
  "confidence": 0.97
}
```

`engine` 枚举：`unity | unreal | cocos | godot | native | flutter | unknown`。  
可多标签：例如 Unity + xLua → `engine=unity`, `hotupdate` 含 `xlua`。

---

## 3. Resource

```json
{
  "id": "res_...",
  "kind": "texture|sprite|atlas|audio|mesh|anim|font|shader|video|prefab|other",
  "name": "enemy_slime",
  "export_path": "textures/enemy_slime.png",
  "original_path": "assets/bin/Data/sharedassets0.assets#123",
  "sha256": "",
  "bytes": 4096,
  "meta": {},
  "referenced_by": ["entity:enemy_slime"]
}
```

---

## 4. EntityTemplate

从 Prefab / 蓝图 / 配置行归一。

```json
{
  "id": "entity:enemy_slime",
  "display_name": "史莱姆",
  "role": "enemy|player|npc|item|spawner|trigger|obstacle|unknown",
  "stats": {"hp": 30, "atk": 5},
  "visuals": ["res_..."],
  "source_table": "table:enemy",
  "evidence": []
}
```

`stats` 的 key 必须来自表列名或代码字段名，不允许翻译成“血量”后丢掉原名。展示名可另存 `display_name`。

---

## 5. Table

```json
{
  "id": "table:enemy",
  "role": "enemy",
  "schema_state": "exact|inferred|unknown",
  "columns": [
    {"name": "id", "type": "int", "semantic": "primary_key"},
    {"name": "hp", "type": "int", "semantic": "stat.hp"}
  ],
  "row_count": 24,
  "path": "ir/tables/enemy.json",
  "preview_rows": [],
  "evidence": []
}
```

大表只在 `ir/tables/` 存全量，顶层只放 preview（≤20 行）与统计：`min/max/null_ratio`。

`role` 枚举：  
`item enemy skill buff level drop shop iap dialogue quest spawn_wave economy_const ui loc other`

---

## 6. Level

```json
{
  "id": "stage_001",
  "index": 1,
  "name": "森林入口",
  "kind": "tilemap_2d|scene_graph_3d|puzzle_board|wave_spawner|runner_segment|ui_only|unknown",
  "rebuild_grade": "L0|L1|L2|L3",
  "size": {"w": 32, "h": 18, "unit": "tile"},
  "unlock": {"requires": ["stage_000"], "stars": 0},
  "win": [{"type": "clear_all_enemies"}],
  "lose": [{"type": "player_dead"}],
  "stars": [],
  "layers": [],
  "entities": [],
  "triggers": [],
  "waves": [],
  "preview": "report/levels/stage_001.png",
  "evidence": []
}
```

`rebuild_grade` 定义见开发文档 7.3。L0 时 `entities` 可空，但 `id` 必须在。

---

## 7. Evidence（强制）

```json
{
  "path": "Assets/Data/EnemyDB.asset",
  "extractor": "unity.scriptable_object",
  "locator": "field:hp",
  "note": "optional"
}
```

策划主张（GDD 只渲染这个数组）：

```json
{
  "id": "claim_econ_01",
  "dimension": 10,
  "severity": "confirmed|hypothesis|unknown",
  "text": "存在体力系统，上限 120，每 6 分钟回复 1 点",
  "confidence": "high|medium|low|hypothesis",
  "evidence": [ { } ]
}
```

`high`：表或代码直接写出。  
`medium`：多处间接证据。  
`low`：弱模式。  
`hypothesis`：允许无硬证据，但必须 `severity=hypothesis`，不能混进 confirmed。  
`confirmed` 且 `confidence!=hypothesis` ⇒ `evidence.length >= 1`。

---

## 8. coverage.json

```json
{
  "resources": {"discovered": 0, "exported": 0, "encrypted": 0, "remote": 0},
  "code": {"java": "ok", "csharp": "dummy_only", "lua": "missing"},
  "levels": {"indexed": 0, "rebuild_l2_plus": 0},
  "tables": {"decoded": 0, "binary_unknown": 0},
  "design_claims": {"high": 0, "medium": 0, "low": 0, "hypothesis": 0},
  "radar": [
    {
      "dimension": "economy",
      "score": 4,
      "max": 5,
      "evidence_count": 12,
      "blockers": ["shop_prices_in_server"],
      "mode_needed_to_improve": "deep"
    }
  ]
}
```

20 维 id 与产品说明书第 5 章一致：  
`identity presentation feel verbs content levels rules combat progression economy monetization social narrative ftue ux liveops network juice analytics tech`

---

## 9. 校验规则（实现时写成官方测试）

1. 所有 `id` 全局唯一。
2. `referenced_by` 指向的 id 必须存在，或显式列在 `unknowns`。
3. `confidence=high|medium|low` 的 claim 必须 `evidence.length >= 1`。
4. `fingerprint.engine=unknown` 时允许 resources 为空，但必须有 `signals`。
5. 不得把原始密钥写入 IR；密钥只存在内存/本地忽略文件，报告仅写 `key_found=true`。
6. `severity=confirmed` 的 claim 必须有 evidence。
7. `share` 产物不得包含 apk/obb/so 与疑似密钥文件。
8. `input_profile.score` 为 0–100；低于 60 时 COVER 必须出现残缺输入警告。
