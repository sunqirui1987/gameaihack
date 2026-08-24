# {{game_title}} — 游戏解剖包

> 这是分析产物，**不是**游戏安装包，也**不是**可商用素材。  
> 工具：gameaihack {{tool_version}}　日期：{{date}}　模式：{{mode}}

## 30 秒结论

{{one_liner}}

- 包名 `{{package_name}}`　版本 {{version_name}}（{{version_code}}）
- 引擎 {{engine}} / {{script_backend}}
- 输入完整度 {{input_score}}/100　{{input_warnings_short}}

## 完整度（0–5）

{{radar_table}}

## 按角色打开

| 你是 | 先看 |
|---|---|
| 制作人 | [COVER.md](COVER.md) |
| 策划 | [design/](design/)　[关卡画廊](levels/gallery.html)　[tables/](tables/) |
| 程序 | [技术](design/08-客户端服务器与技术.md)　[machine/](machine/)　[手感](feel/inventory.md) |
| 美术/音频 | [assets/](assets/)　[表现](design/01-身份证与循环.md) |
| 用脚本/AI 接 | [machine/game.ir.json](machine/game.ir.json)　[claims.json](design/claims.json) |

总览页：[index.html](index.html)（若图片空白，见 `OPEN.txt`）

## 不要做

- 不要二次分发原画、音频、本包
- 不要把这里的资源当素材上架或训练公开模型（除非权利人书面允许）
- 不要假设缺失的关卡/概率「被工具漏了」——先看 [未知项](design/09-未知项.md)

## 本包用了什么输入

见 [input_profile.json](input_profile.json)。没有列出的 OBB/热更，覆盖率会偏低。

权利说明：[LEGAL.txt](LEGAL.txt)
