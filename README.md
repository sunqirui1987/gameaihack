# GameAIHack

给一个 **Google Play 包名**，解包到 `raw/`，抽出美术到 `output/美术/`，再用 **DeepSeek Harness（必须）** 读 raw + 美术，写出完整策划到 `output/策划/`。过程写在 `output/策划/过程.md` 和 `raw/dsh.log`。

```bash
# DSH 必须。默认 node 23 不行，用 22 或 24：
export PATH="$HOME/.nvm/versions/node/v22.18.0/bin:$PATH"
mkdir -p .dsh && npm install --prefix .dsh @deepseek-ai/dsh

# 模型：Grok。密钥和 llm_bench 一样
export LLM_API_KEY=sk-xxxx
export LLM_BASE_URL=http://127.0.0.1:8080
export LLM_MODELS=grok-4.6

pip install -e .
gameaihack doctor    # dsh、llm 必须过
gameaihack analyze com.unciv.app
```

输出：

```
jobs/com.rovio.baba/
  raw/                 解包原始数据（DSH 读这里）
  output/              最终成品（DSH 写的策划 + 抽出的美术）
    策划/              完整策划稿（产品、玩法、按章关卡…）
    策划/关卡/第001章.md
    美术/              抽出的图 / 音 / 字
```

没有 dsh 或没有密钥会直接失败，不会静默跳过。

同一包名第二次用 `samples/` 缓存和已有 `raw/`，不重下。强制重下：`--force-fetch`。

发给别人（zip 是 `output/`，不含原包）：

```bash
gameaihack share ./jobs/<包名> --to ./结果.zip
```
