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

策划必须对着机器写的**事实源**（`output/策划/_事实源.md` = raw 清单 + 美术清单）来写：不能发明事实源里没有的目录或系统。程序只看 `02-核心玩法.md` 要能做第一局。

---

## 安装

需要 Python 3.10+。

```bash
pip install -e .
bash scripts/bootstrap_macos.sh   # apktool / jadx / Il2CppDumper
cp .env.example .env              # 填 LLM_*
gameaihack doctor
```

默认分析通道是**自建 agent**，只要 OpenAI 兼容网关，不必安装 grok / Codex CLI。

```
LLM_API_KEY=...
LLM_BASE_URL=https://your-gateway.example/v1
LLM_MODELS=gpt-5.4
```

也认 `OPENAI_API_KEY` / `OPENAI_BASE_URL`。模型名以网关为准。

---

## 两种 Agent 模式

| `--via` | 模式 | 需要什么 |
|---|---|---|
| `sdk`（默认，别名 `agent`） | **自建 agent**：进程内工具循环，HTTP `chat/completions` | 只配 `LLM_*`，不要 grok/codex CLI |
| `grok` / `codex` / `dsh` | **本机 CLI**：用 grok / Codex / DSH 的本地 agent 能力 | 对应二进制在 PATH；有 `LLM_*` 时按 Cindy harness 注入，不绑官方账号 |

自建 agent 自带工具：`list_dir` / `tree` / `glob` / `grep` / `read_file` / `write` / `search_replace`。只能写 `output/策划/` 和清单，不能改 `raw/`、`_事实源.md`。看美术先 `list_dir output/美术` 看文件夹计数，不要枚举上万 PNG。

本机 CLI 模式学 Cindy 的宿主注入：把 **model + baseUrl + key** 写进子进程环境，并给独立的 `GROK_HOME` / `CODEX_HOME`（在 `raw/_cli_home/`），不读 `~/.codex`、不把网关模型塞进官方 `/responses`。没配 `LLM_*` 时，CLI 用自己的本机登录。

```bash
gameaihack analyze com.rovio.baba --i-have-rights
# 同上，显式自建 agent
gameaihack analyze com.rovio.baba --via sdk --i-have-rights

# 本机 grok CLI（注入 LLM_*）
gameaihack analyze com.rovio.baba --via grok --i-have-rights

# 本机 Codex CLI
gameaihack analyze com.rovio.baba --via codex --i-have-rights

# DeepSeek Harness
gameaihack analyze com.rovio.baba --via dsh --i-have-rights
```

环境变量 `GAMEAIHACK_VIA=sdk|grok|codex|dsh` 与 `--via` 相同。推理深度默认 `xhigh`（`GAMEAIHACK_EFFORT`）。

网关若只提供 OpenAI Responses（`/v1/responses`），再设 `LLM_API_BACKEND=responses`。默认走 Chat Completions，避免 Codex 打到官方 `/responses` 404。

控制台按 think / write / tools 分组滚动，不写 `过程.md`。

---

## 命令

```bash
gameaihack doctor
gameaihack inspect  <apk|xapk|包名>
gameaihack fetch    <包名>                 # 下到 samples/
gameaihack analyze  <apk|xapk|包名>
            --via sdk|grok|codex|dsh
            --mode brief|standard|deep
            --i-have-rights              # 非 TTY / CI 必须带
            --force-fetch                # 忽略 samples/ 缓存
gameaihack share    ./jobs/<包名> --to ./结果.zip
```

同一包名第二次：已有 `raw/` 就跳过解包。每次**清空整个 `output/策划` 和说明**再从零写，**保留美术**（重抽很慢）。已抽出的 Unity 容器按 mtime 跳过；并行抽图用 `GAMEAIHACK_ART_JOBS`（默认 CPU，最多 8）。

zip 只含 `output/`，不含原包：

```bash
gameaihack share ./jobs/<包名> --to ./结果.zip
```

发给别人先读 `output/复刻说明.md`。总清单：`jobs/<包>/清单.md`。运行日志：`jobs/<包>/run.log`。
