# GameAIHack

给一个游戏包名，产出一份**新游戏制作材料包**：`output/美术`（对照图）+ `output/策划`（可直接开工的制作说明书，含整局流程、系统、关卡、图鉴）。用自己的引擎重做，不是重打包原 APK。

Agent 工作区是 `jobs/<包>/`：

- `raw/` 原始解包数据，只读
- `output/` 要生成的结果（策划写这里；美术已抽出）

通道和 llm_bench 一样，用 `--via grok|codex|dsh`（默认 grok）。**不用 HTTP 直连补全。**

```bash
# 密钥（dsh 需要；grok/codex 走各自 CLI）
export LLM_API_KEY=sk-xxxx
export LLM_BASE_URL=http://127.0.0.1:8080
export LLM_MODELS=grok-4.6

pip install -e .
bash scripts/bootstrap_macos.sh   # apktool / jadx / Il2CppDumper
gameaihack doctor
gameaihack analyze com.rovio.baba --via grok
# 或 --via codex / --via dsh
```

输出：

```
jobs/<包名>/
  raw/                      原始解包（agent 只读）
  output/
    复刻说明.md             怎么用策划+美术做新游戏
    策划/                   制作说明书：核心玩法、制作顺序、系统、关卡、图鉴
    美术/                   抽出的 PNG
```

总清单在 `jobs/<包>/清单.md`。运行日志：`jobs/<包>/run.log`。Agent 输出格式与 grok/codex CLI 相同（think / write / tools）。

同一包名第二次：已有 `raw/` 就跳过解包；每次**清空整个 `output/策划` 和说明**再从零写核心玩法，**保留美术**（重抽很慢）。强制重下包：`--force-fetch`。已抽出的 Unity 容器按 mtime 跳过；并行抽图用 `GAMEAIHACK_ART_JOBS`（默认 CPU，最多 8）。

发给别人（zip 是 `output/`，不含原包）：

```bash
gameaihack share ./jobs/<包名> --to ./结果.zip
```
