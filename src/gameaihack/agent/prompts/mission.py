"""全仓库唯一任务文案。所有 AGENTS.md、Persona、DRIVE、README 都从这里出。

产品：提取原作的策划与美术，再用 TapTap Maker 做成玩法一模一样的新游戏。
"""

from __future__ import annotations

GOAL = "提取这款游戏的策划和美术，再用 TapTap Maker 做成玩法一模一样的新游戏。"

INSTALL_CMD = "npx -y @taptap/maker install --ide codex,cursor,claude"
INIT_CMD = "npx -y @taptap/maker init"

CONSTRAINTS = (
    "不重打包原 APK，不写盗版客户端。"
    "不分析广告、内购、抽卡、市场。"
    "玩法必须一样：操作、场上物、胜负、每一关干什么。"
    "角色名、Logo、IP 换成自己的。"
    "不要建 tests/。"
    "Lua 不要用 os.clock()、io.*；时间用 eventData[\"TimeStep\"]:GetFloat()。"
    "不要改 raw/ 和 策划/_事实源.md。"
)

# 给各通道的系统人格（短）
PERSONA = (
    f"{GOAL}"
    "机器只解了包。"
    "1) 执行 gameaihack art . 把贴图和音抽到 output/assets/；"
    "2) 把 output/策划/02-核心玩法.md 写成完整游戏 PRD 设计稿（细到能直接开发，不是摘要）；"
    "3) 在 output/ init Maker，用抽出的图写 scripts/，做成能玩的同一套游戏。"
    f"{CONSTRAINTS}"
)

# job 根 AGENTS.md
JOB_AGENTS = f"""# AGENTS.md

{GOAL}

机器只解了包。一次做完：

1. **美术** `gameaihack art .` → `output/assets/image/`、`output/assets/audio/`（玩法用图，不是运营素材墙）
2. **策划** `output/策划/02-核心玩法.md` 必须是**游戏 PRD 设计稿**（核心循环、操作规格、每个场上物、规则数值、一局时序、HUD、第一关可开发规格、验收标准）。关卡表用第几关 / 干什么 / 通关开哪
3. **新游戏** 在 `output/` 执行 `{INIT_CMD}`，把玩法写进 `output/scripts/main.lua`，贴图用 `assets/image/`。至少第一关能打完

{CONSTRAINTS}
"""

# raw/ AGENTS.md
RAW_AGENTS = f"""# AGENTS.md — raw

解包数据。用来提取**策划**（怎么玩）和对照 **美术**，再做到 Maker 里。

- `unpacked/` APK
- `extract/normalized/` 配置 / 脚本
- `ir/` 机器索引

不要读 apk/so/dex。不要分析广告和内购。
玩法写成 `../output/策划/02-核心玩法.md`（游戏 PRD，不是短介绍）。
贴图抽到 `../output/assets/image/`，在 Lua 里引用这些路径。
{CONSTRAINTS}
"""

# 02-核心玩法.md 必须按这个 PRD 写。交差会检查这些标题。
PRD_NEEDLES: list[tuple[str, tuple[str, ...]]] = [
    ("核心循环", ("核心循环",)),
    ("操作规格", ("操作规格", "操作")),
    ("场上物", ("场上物",)),
    ("规则与数值", ("规则与数值", "胜负")),
    ("一局流程", ("一局流程", "一局时间线")),
    ("局内界面", ("HUD", "局内界面")),
    ("第一关", ("第一关",)),
    ("验收标准", ("验收标准", "验收")),
    ("未知项", ("未知项", "还不知道")),
]

PLAY_PRD = """
## `02-核心玩法.md` = 游戏 PRD 设计稿（必须非常详细）

这一篇不是介绍，不是摘要，是**给程序直接开发的 PRD**。
只读这一篇，要能在 Maker 里做出同一套核心玩法，不必再猜。
宁可写长，也不要几句话带过。没证据的参数写「未知」，禁止编造成确定数字。

必须按下面章节写，标题尽量原样保留：

### 1. 文档范围
- 一句话：这游戏玩的就是什么。
- 本文覆盖：核心玩法、一局流程、第一关。不覆盖商业化。
- 读完本文应该能做什么：做出能打完的第一局。

### 2. 体验目标
- 玩家每一局在干什么、怎样算「打得爽」。
- 成功时看到/听到什么；失败时看到/听到什么。未知就写未知。

### 3. 核心循环
逐步写，每一步包含：玩家输入 → 系统立刻做什么 → 画面上什么变了。
必须覆盖：进关 → 开打 → 操作过程 → 判定 → 反馈 → 赢/输 → 结算 → 再来或下一关。
不要写成「核心循环是射击」这种一句话。

### 4. 操作规格
**每一种操作单独一小节**（点、按住、拖、松手、多指等，原作有几种写几种）。每种写清：
- 何时可用（哪个界面、关内还是关外）
- 怎样触发（按下/移动/松开、作用在谁身上）
- 进行中每帧发生什么
- 结束时发生什么
- 取消/点空/拖出屏幕会怎样
- 和哪个场上物绑定
手感参数（力度、角度、冷却）有证据再写数字，否则写未知。

### 5. 场上物规格
**每一个会参与玩法的物单独一小节**（玩家用的、要打的、挡路的、会动的、会触发的、弹药、终点等）。每个写清：
- 人话名称（不要 Unity 类名）
- 对应资源：`assets/image/...`（没有就写未知）
- 出现时机（开局就有 / 打中才出 / 某关才有）
- 在场上干什么
- 碰撞：碰到谁、结果是什么（碎、弹开、得分、扣弹药、过关…）
- 何时消失
- 关卡之间会不会变
用表格或固定小标题，不要混成一段散文。

### 6. 规则与数值
- 怎样算赢，条件写完整（打完所有目标？碰到终点？分数？）
- 怎样算输（弹药用尽、掉出界、时间到…）
- 一局有哪些限制（弹药、生命、时间、步数）
- 星级/评分（有才写）
- 能从 raw 里读到的数字照抄并注明来源路径；读不到就列「未知」，不要编。

### 7. 一局流程（时序 PRD）
从点「开始」到结算按钮，按时间顺序逐步写。每一步：谁、做什么、界面上出现什么、下一步是什么。
包括：进关、倒计时有无、第一动、中途暂停有无、过关/失败演出、结算选项（再来 / 下一关 / 回大厅）。

### 8. 局内界面（HUD）
每个局内元素：名字、在屏幕哪一侧、显示什么、能不能点、点了发生什么。
不要写大厅商城、活动、公会。

### 9. 第一关 PRD（必须能单独开发）
这一节要细到程序不用问第二句：
- 场上初始有哪些物、彼此位置关系（左/右/上/下/远近；没有坐标就不要假装有坐标）
- 玩家目标
- 正确打法逐步（第一下做什么、然后什么、最后怎样过关）
- 打完开什么；失败回哪
- 这一关新教的操作（如果有）

### 10. 关卡变化规则
- 核心操作哪些关都不变
- 后面关相对第一关会加什么物、什么规则、什么限制
- 关数未知就写「关数未知」，不要用每章 5 关占位冒充原作

### 11. 反馈（Juice）
命中、失败、过关的反馈。有证据写；没有就「未知」。

### 12. Maker 实现约束
- 2D 触屏、用已提取的 `assets/image/`
- 时间用 TimeStep，禁止 os.clock / io
- 本文 PRD 是实现唯一依据

### 13. 验收标准
列出程序按本文做完第一关后必须为真的条目（至少 8 条），例如：
- 规定的操作都能用，且效果与本文一致
- 场上物种类与碰撞结果与本文一致
- 赢/输条件与本文一致
- 用的是提取的贴图，不是空白方块凑数

### 14. 未知项
专章列表：还缺的规则、数值、坐标、资源。每条写「下一步去 raw 哪里找」。禁止用猜测填成正文里的确定句。
"""

DRIVE = f"""# 任务

{GOAL}

`output/` 就是 TapTap Maker 工程。交差不是只交 markdown，而是做出玩法一样的新游戏。

机器只解了包（`raw/`）。工作区是这个 job。一次做完，不要等下一轮。

{CONSTRAINTS}

---

## 成功线

1. **美术已提取**：`output/assets/image/` 里有从原包抽出的贴图（`gameaihack art .`）。
2. **策划已提取**：`策划/02-核心玩法.md` 是完整 **游戏 PRD 设计稿**（见下方必有章节），细到程序不用再猜。关卡表用人话：第几关 / 干什么 / 通关开哪。
3. **新游戏已做成**：`scripts/main.lua` 严格按这份 PRD、用 `assets/image/` 实现同一套核心玩法（至少第一关能打完）。`output/` 已 init 成 Maker 工程。

没有第 3 条，前面写得再完整也不算完成。

---

## 顺序

1. **提取美术**
   在 job 根目录执行：`gameaihack art .`
   贴图 → `output/assets/image/{{sprites,world,ui,fx}}/`
   音 → `output/assets/audio/`
   读 `output/assets/清单/给策划.md`。

2. **提取策划**
   `策划/02-核心玩法.md` **就是游戏 PRD**，按下面「必有章节」写全、写细。
   没证据标未知，禁止编造。不写商业化。

3. **用 Maker 做成一模一样的新游戏**
   没有 `.project/project.json` 就在 `output/` 执行：
   `{INIT_CMD}`
   MCP：`{INSTALL_CMD}`
   然后写 `scripts/`：用已提取的 `assets/image/`，按 02 实现同一套玩法。

---
{PLAY_PRD}
---

## 其它策划文件

- `README.md` `制作顺序.md`：先做出能打完的一局，再加关。
- `00-封面.md` `01-产品定位.md`：玩法是什么，不是市场。
- `03-关卡设计.md`、`策划/关卡/README.md`：第几关 / 干什么 / 通关开哪。
- `04-成长与进度.md`：只写会改玩法的解锁。
- `05-经济与商业化.md`：只写「不分析商业化」。
- `06-系统总表.md`：玩法系统。
- `07-新手-UI-社交.md`：怎么学会玩、局内 HUD。
- `08-技术约束.md`：这套玩法在 Maker 2D 物理里怎么搭。
- `09-未知与下一步.md`：玩法证据缺口。
- 图鉴按提取出来的资源文件夹写：图在场上干什么。

事实源：`output/策划/_事实源.md`、`output/assets/清单/给策划.md`、`raw/清单/给策划.md`。
禁止发明没有的目录；禁止用机器编号当关卡主列。
"""


def output_agents(pkg: str) -> str:
    return f"""# AGENTS.md · {pkg}

{GOAL}

本目录（`output/`）就是 TapTap Maker 工程。

## 已提取

- 美术：`assets/image/`、`assets/audio/`（从原包抽出，给新游戏用）
- 策划：`策划/02-核心玩法.md` 是游戏 PRD 设计稿，按它开发

## 新游戏

- 写 `scripts/main.lua`，用 `assets/image/` 做成**玩法一模一样**的新游戏
- 构建 / 预览：`maker_build`
- 先 `maker_status`；未登录 `maker_login`
- 缺 `.project/project.json` 时在本目录 `{INIT_CMD}`
- 引擎知识在 `engine-docs/`、`examples/`、`urhox-libs/`，分析用户代码时忽略

{CONSTRAINTS}
"""


def output_readme(pkg: str, *, status: str, extra: str = "") -> str:
    return f"""# {pkg} · TapTap Maker

{GOAL}

本目录就是 Maker 工程。不要重打包原 APK。

{status}{extra}
## 目录

```
./
  策划/              提取出的玩法（02-核心玩法.md 是中心）
  assets/image/      提取出的美术（sprites/world/ui/fx）
  assets/audio/
  scripts/           新游戏（玩法必须一样）
  美术/              与 assets/image 同一批图
```

## 一、安装 Maker MCP

```bash
{INSTALL_CMD}
```

## 二、初始化

若还没有 `.project/project.json`：

```bash
{INIT_CMD}
```

## 三、做成一模一样的新游戏

`scripts/main.lua` 必须按 [策划/02-核心玩法.md](策划/02-核心玩法.md) 这份 **PRD** 实现同一套核心玩法。
贴图用 [assets/image/](assets/image/)。`maker_build` 预览。
角色名、Logo 换成自己的。
"""


def job_readme(pkg: str) -> str:
    return f"""# {pkg}

{GOAL}

| 目录 | 是什么 |
|---|---|
| [清单.md](清单.md) | 总清单 |
| [raw/](raw/) | 解包，不外发 |
| [output/](output/) | **TapTap Maker 工程 = 新游戏** |
| [output/策划/](output/策划/) | 提取出的玩法 |
| [output/assets/](output/assets/) | 提取出的美术 |
| [output/scripts/](output/scripts/) | 新游戏代码 |
| [run.log](run.log) | 运行日志 |

不要重打包原 APK。
"""


HOW_TO_REMAKE = """## 怎么做成新游戏

1. 读 [output/策划/02-核心玩法.md](output/策划/02-核心玩法.md)（游戏 PRD 设计稿）
2. 贴图在 [output/assets/image/](output/assets/image/)（提取出的美术）
3. 把同一套玩法写进 [output/scripts/main.lua](output/scripts/main.lua)
4. 不要重打包原 APK。角色名、Logo 换成自己的
"""
