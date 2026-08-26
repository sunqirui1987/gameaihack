# GameAIHack

提取这款游戏的**策划**和**美术**，再用 **TapTap Maker** 做成玩法一模一样的新游戏。版本 `0.2.0`。

机器只解包。**Codex / Grok / DSH / SDK** 跑同一份任务（文案只在 `src/gameaihack/agent/prompts/mission.py`）：

1. **提取美术** → `output/assets/image/` `output/assets/audio/`
2. **提取策划** → `output/策划/02-核心玩法.md`（**游戏 PRD 设计稿**，必须非常详细）
3. **做成新游戏** → `output/scripts/`（按 PRD 实现同一套玩法，至少第一关能打完）

`output/` 就是 Maker 工程。不重打包原 APK。不分析商业化。角色名、Logo 换成自己的，玩法必须一样。

方案与命令见 [docs/](docs/README.md)。

```
jobs/<包名>/
  raw/                 解包（不外发）
  output/              Maker 工程 = 新游戏
    策划/02-核心玩法.md   游戏 PRD
    assets/image/        提取的美术
    scripts/             新游戏
```

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dsh]'
bash scripts/bootstrap_macos.sh
cp .env.example .env
gameaihack doctor
```
