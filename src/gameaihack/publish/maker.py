"""把 output/ 写成 TapTap Maker 工程目录，给 Cindy 按策划做第一局。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from gameaihack.core.layout import MAKER_KEEP, output_dir  # noqa: F401

INSTALL_CMD = "npx -y @taptap/maker install --ide codex,cursor,claude"
INIT_CMD = "npx -y @taptap/maker init"


def emit_maker_project(job_dir: Path, ir: dict | None = None, *, run_init: bool | None = None) -> dict:
    """output/ 就是 Maker 工程：scripts/、assets/、AGENTS.md，策划在 策划/。

    有 npx 时尝试在 output/ 执行 `npx -y @taptap/maker init`。
    init 成败都会写 README / AGENTS.md，并印上 MCP 安装命令。
    """
    job_dir = Path(job_dir)
    dest = output_dir(job_dir)
    dest.mkdir(parents=True, exist_ok=True)
    ir = ir or {}
    pkg = ((ir.get("package") or {}).get("name") or job_dir.name).strip() or job_dir.name
    if run_init is None:
        run_init = not bool(os.environ.get("PYTEST_CURRENT_TEST"))
        if (os.environ.get("GAMEAIHACK_MAKER_INIT") or "").strip() in {"0", "off", "false"}:
            run_init = False
    inited = (dest / ".project" / "project.json").is_file() or (dest / "engine-docs").is_dir()
    init_ok = inited
    init_note = "已有 Maker 工程，跳过 init" if inited else ""
    if run_init and not inited:
        init_ok, init_note = _run_maker(["init"], dest, timeout=180)
    (dest / "README.md").write_text(_readme(pkg, init_ok, init_note), encoding="utf-8")
    (dest / "AGENTS.md").write_text(_agents(pkg), encoding="utf-8")
    scripts = dest / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    main = scripts / "main.lua"
    if not main.is_file():
        main.write_text(_stub_lua(pkg), encoding="utf-8")
    for sub in ("image", "audio", "sprites"):
        (dest / "assets" / sub).mkdir(parents=True, exist_ok=True)
    return {
        "path": str(dest),
        "init": bool(init_ok),
        "note": init_note,
        "install": INSTALL_CMD,
        "init_cmd": INIT_CMD,
    }


def _run_maker(args: list[str], cwd: Path, *, timeout: int) -> tuple[bool, str]:
    npx = shutil.which("npx")
    if not npx:
        return False, "没有 npx（需要 Node）。目录骨架已按 Maker 工程写出，可稍后在 output/ 执行 init。"
    cmd = [npx, "-y", "@taptap/maker", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "1", "npm_config_yes": "true"},
        )
    except subprocess.TimeoutExpired:
        return False, f"{' '.join(cmd)} 超时"
    except OSError as e:
        return False, str(e)
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return False, text[:800] or f"退出码 {proc.returncode}"
    return True, text[:400] or "ok"


def _readme(pkg: str, init_ok: bool, init_note: str) -> str:
    status = "已在本目录执行 `npx -y @taptap/maker init`。" if init_ok else "Maker 目录骨架已写出，init 还没跑成。"
    extra = f"\n\n> {init_note}\n" if init_note and not init_ok else "\n"
    return f"""# TapTap Maker 工程 · {pkg}

**本目录就是 Maker 工程。** 用 Cindy 打开这里（`output/`），按 `策划/` 做一款玩法相同的新游戏。不要重打包原 APK。

{status}{extra}
## 目录

```
./
  AGENTS.md          Cindy / Maker 怎么开工
  scripts/           Lua，入口 main.lua
  assets/image/      上架用图（生成/重绘，不要用原包 PNG）
  assets/audio/
  策划/              对照说明书
  美术/              解包对照图，只说明构图
```

## 一、安装 Maker MCP

部分 Agent 安装后可能需要重新启动。

```bash
{INSTALL_CMD}
```

## 二、初始化项目

若还没有 `.project/project.json`，就在**本目录**执行：

```bash
{INIT_CMD}
```

从零开始：选一个空白本地目录，进去再执行同一条。分析流水线会尽量已经帮你 init 过。

## 三、用 Cindy 做第一局

1. 用 Cindy 打开本目录。
2. 按 taptap-maker skill：先 `maker_status`，未登录则 `maker_login`。
3. 读 [策划/02-核心玩法.md](策划/02-核心玩法.md) 和 [策划/制作顺序.md](策划/制作顺序.md)。
4. 在 `scripts/main.lua` 做出第一局（2D 物理、能胜能负）。
5. `maker_build` 预览。

对照图在 [美术/](美术/)。上架图请生成到 `assets/image/`。IP、角色名、Logo 全部换成自己的。
"""


def _agents(pkg: str) -> str:
    return f"""# AGENTS.md · {pkg}

这是 **TapTap Maker** 工程（分析产出的 `output/`）。实现时走 Maker 插件，不要当普通 Git 仓库提交。

## Maker

- 构建 / 预览 / 跑一下：`maker_build`。
- 先 `maker_status`；未登录 `maker_login`。
- 缺 `.project/project.json` 时在本目录 `{INIT_CMD}`。
- 素材生成到 `assets/image`、`assets/audio`。`美术/` 只对照，不要当商用素材。
- Lua 不要用 `os.clock()`、`io.*`。时间用 `eventData["TimeStep"]:GetFloat()`。
- 引擎知识在 `engine-docs/`、`examples/`、`urhox-libs/`，分析用户代码时忽略这些目录。

## 策划

1. [策划/README.md](策划/README.md)
2. [策划/02-核心玩法.md](策划/02-核心玩法.md)（只看这篇要能做第一局）
3. [策划/制作顺序.md](策划/制作顺序.md)
4. [策划/图鉴/README.md](策划/图鉴/README.md)

不要改 `策划/_事实源.md`，不要改 `../raw/`。不要重打包原 APK。

## 第一局

横屏 16:9。2D 物理（Box2D）。左侧玩家工具、右侧目标。触屏拖、松手发射。打完目标为胜，弹药用尽为负。结算：再来 / 回大厅。

脚本入口：`scripts/main.lua`。
"""


def _stub_lua(pkg: str) -> str:
    return f"""-- {pkg} · TapTap Maker 第一局入口
-- 对照 策划/02-核心玩法.md 实现。不要用 os.clock / io。

local UI = require("urhox-libs/UI")

function Start()
    UI.Init({{ fonts = {{ {{ family = "sans", weights = {{ normal = "Fonts/MiSans-Regular.ttf" }} }} }} }})
    print("TODO: 按策划做第一局。然后 maker_build 预览。")
end

function Stop()
    UI.Shutdown()
end
"""
