# GameAIHack

给一个游戏包名或安装包，产出一份**新游戏制作材料包**：对照美术 + 可直接开工的策划说明书。用自己的引擎重做，不是重打包原 APK。

```
jobs/<包名>/
  raw/                 解包数据（agent 只读，不外发）
  output/
    复刻说明.md         怎么用策划 + 美术做新游戏
    策划/               制作说明书：核心玩法、制作顺序、系统、关卡、图鉴
    美术/               抽出的 PNG + 清单
  清单.md               包名下总清单
```

策划必须对着机器写的**事实源**（`output/策划/_事实源.md` = raw 清单 + 美术清单）来写。程序只看 `02-核心玩法.md` 要能做第一局。

---

## 安装

Python 3.10+。默认 agent 是 [DeepSeek Harness Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md)（捆绑 runtime，不需要 Node）。

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dsh]'
bash scripts/bootstrap_macos.sh
cp .env.example .env
gameaihack doctor
```

```
LLM_API_KEY=...
LLM_BASE_URL=https://your-gateway.example/v1
LLM_MODELS=gpt-5.4
```

也认 `OPENAI_*` / `DEEPSEEK_*`。macOS 的 `runtime-bin` 是 arm64 wheel；venv 不要用 Rosetta x86_64 Python。

---

## 两种 Agent 模式

| `--via` | 模式 |
|---|---|
| `sdk`（默认） | 自建 agent：官方 `DeepSeekHarness`，工作区是 job，工具是 DSH 的 bash + 编辑器 |
| `grok` / `codex` / `dsh` | 本机 CLI。有 `LLM_*` 时注入网关；没有则用 CLI 自己的登录 |

```bash
gameaihack analyze com.rovio.baba --i-have-rights
gameaihack analyze com.rovio.baba --via grok --i-have-rights
gameaihack share ./jobs/<包名> --to ./结果.zip
```

同一包名第二次：已有 `raw/` 就跳过解包；每次清空 `output/策划`，保留美术。
