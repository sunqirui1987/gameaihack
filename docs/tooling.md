# 工具清单与调用约定

全部外部工具经 `src/gameaihack/tools/` wrapper 调用，版本写入 `run_manifest.json`。  
缺失工具时：该 adapter 记失败原因，不让整个 job 崩溃。

---

## 通用 APK

| 工具 | 用途 | 调用 |
|---|---|---|
| unzip / Python zipfile | 解 APK/XAPK/OBB | 内置 |
| [apktool](https://apktool.org/) | Manifest、resources.arsc、可选 smali | `apktool d -s -o <dir> <apk>` |
| [jadx](https://github.com/skylot/jadx) | Java/Kotlin 反编译 | `jadx -d <out> <apk>` |
| aapt2 | 包名、权限、activity 快读 | `aapt2 dump badging` |
| androguard（可选） | DEX 特征 | Python API |

Split / Play Asset Delivery：

- `.xapk` / `.apks` 当 zip，找出 `base.apk` 与 `*.apk` 合并 `assets/`、`lib/`。
- `.obb` 优先当 zip，失败则当 Unity/Unreal 容器交给对应 adapter。

---

## Unity

| 工具 | 用途 | 备注 |
|---|---|---|
| [UnityPy](https://github.com/K0lb3/UnityPy) | 按类型导出 Texture/Audio/TextAsset/MonoBehaviour | 第一期默认，纯 Python |
| [AssetRipper](https://github.com/AssetRipper/AssetRipper) CLI | Scene/Prefab YAML、更完整工程树 | 第二优先，体积大 |
| [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) | dummy dll + script.json | 还原字段名刚需 |
| [Cpp2IL](https://github.com/SamboyCoding/Cpp2IL) | 尝试恢复 IL | 质量不稳定，仅辅助 |
| ILSpy / dnlib | Mono dll → C# | |
| AssetStudio 系 | 人工复查 GUI，不进 CI | |

IL2CPP 最小顺序：

1. 找 `libil2cpp.so`（优先 arm64）+ `global-metadata.dat`
2. Il2CppDumper → `DummyDll/`
3. 把 DummyDll 交给 AssetRipper / UnityPy 的 type tree
4. 只对 `LevelLoader`、`TableMgr`、`Shop`、`Battle` 等少量类考虑 Ghidra（人工或后续自动化）

UnityCN / 加密 bundle：先在 so 与 `assets` 搜 key 字符串，再解密。找不到则进 runtime 队列。

---

## Cocos

| 工具 | 用途 |
|---|---|
| xxtea 解密（自研小模块或 cocos2dx-xxtea-decryptor） | `.jsc` `.luac` `.bytes` |
| unluac / LuaJIT 反编译 | bytecode → lua |
| TexturePacker plist 解析 | 图集拆图 |
| Tiled tmj/tmx | 关卡 |

密钥：静态扫 `libcocos2d*.so` 中与 `xxtea` / `sign` 相邻的 ASCII；失败再 Frida dump 解密函数参数。只保存明文资源。

---

## Unreal

| 工具 | 用途 |
|---|---|
| [CUE4Parse](https://github.com/FabianFG/CUE4Parse) | pak/ucas 解析 |
| [FModel](https://fmodel.app/) | 人工浏览，CLI 可选 |
| usmap | UE5 unversioned property 必需，没有则表/蓝图字段名会丢 |

---

## Godot / 其他

- Godot：`pck` 提取；`.tscn` 直接收口到 IR。
- Native：jadx + 文件头嗅探（png/ogg/wav/json/zip/protobuf）。
- 加固：只标记厂商特征（文件名、so 符号），脱壳不作为第一期功能。

---

## 运行时 dump（可选、受限）

依赖：adb、官方包可安装的模拟器或真机、Frida。

允许的脚本类型：

- hook 文件读取，写解密后 buffer 到 `extract/runtime/`
- hook XXTEA/AES decrypt，保存 key_found 布尔值与明文文件

不允许：

- 改内存数值、改支付、绕过登录、重打包签名去广告

---

## LLM

用途仅限：

- 表 `role` 打标
- 关卡 kind 分类（规则分数接近时）
- GDD 章节撰写（必须带 evidence）
- 资源/界面的人类可读命名

模型配置放 `configs/pipeline.yaml`，默认兼容 OpenAI API。无密钥时跳过合成，仍产出 IR 与资源墙。

---

## 版本锁定示例

`tools/versions.lock`：

```
apktool==2.11.1
jadx==1.5.1
unitypy==1.22.5
il2cppdumper==6.7.46
```

job 的 `run_manifest.json` 复制一份，保证复跑可比对。
