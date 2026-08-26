from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass


@dataclass
class Check:
    name: str
    ok: bool
    required: bool
    detail: str


def run_doctor() -> tuple[list[Check], bool]:
    checks: list[Check] = []
    py_ok = sys.version_info >= (3, 10)
    checks.append(
        Check(
            "python>=3.10",
            py_ok,
            True,
            f"{sys.version.split()[0]}",
        )
    )
    for mod, req in (("yaml", True), ("jinja2", True), ("jsonschema", True), ("typer", True)):
        try:
            __import__(mod)
            checks.append(Check(mod, True, req, "import ok"))
        except ImportError as e:
            checks.append(Check(mod, False, req, str(e)))
    for mod, why in (
        ("pyaxmlparser", "读包名"),
        ("UnityPy", "Unity 资源"),
        ("PIL", "贴图导出"),
    ):
        try:
            __import__(mod)
            checks.append(Check(mod, True, False, why + " · import ok"))
        except ImportError:
            checks.append(Check(mod, False, False, "未安装，" + why + "将降级"))

    from gameaihack.core.fs import which_exe

    for exe, req, why in (
        ("apktool", False, "解码 Manifest/resources"),
        ("jadx", False, "Java 反编译"),
        ("Il2CppDumper", False, "IL2CPP dummy dll"),
        ("adb", False, "deep 模式 pull 缓存"),
        ("frida", False, "deep 明文 dump（可选）"),
        ("docker", False, "推荐分发方式"),
        ("npx", False, "写出 TapTap Maker 工程时执行 init"),
        ("gplaydl", False, "按包名从 Play 下载（需 gplaydl link）"),
    ):
        names = (exe, "il2cppdumper") if exe == "Il2CppDumper" else (exe,)
        path = which_exe(*names)
        checks.append(Check(exe, bool(path), req, path or why))

    from gameaihack.agent.drivers.codex import which_codex
    from gameaihack.agent.drivers.dsh import dsh_argv
    from gameaihack.agent.drivers.grok import which_grok

    grok = which_grok()
    checks.append(Check("grok-cli", bool(grok), False, grok or "可选 --via grok（本机 CLI）"))
    codex = which_codex()
    checks.append(Check("codex-cli", bool(codex), False, codex or "可选 --via codex（本机 CLI）"))
    dsh = dsh_argv()
    checks.append(
        Check("dsh-cli", bool(dsh), False, " ".join(dsh) if dsh else "可选 --via dsh（npm CLI）")
    )
    try:
        import deepseek_harness  # noqa: F401

        from gameaihack.agent.drivers.sdk import resolve_runtime_bin

        runtime = resolve_runtime_bin()
        if runtime:
            checks.append(Check("dsh-sdk", True, True, f"DeepSeekHarness · {runtime}"))
        else:
            checks.append(
                Check(
                    "dsh-sdk",
                    False,
                    True,
                    "SDK 已装，缺 runtime-bin（macOS 14+ arm64 wheel；Rosetta 见 README）",
                )
            )
    except ImportError:
        checks.append(
            Check(
                "dsh-sdk",
                False,
                True,
                "pip install deepseek-harness-sdk（自建 agent 默认通道）",
            )
        )

    from gameaihack.agent.llm import resolve_llm

    llm = resolve_llm()
    if llm:
        checks.append(
            Check("llm", True, True, f"{llm.source} · {llm.model} · {llm.base_url}")
        )
        checks.append(
            Check(
                "agent",
                True,
                True,
                "默认 --via sdk = DeepSeek Harness SDK；--via grok|codex|dsh = 本机 CLI",
            )
        )
    else:
        checks.append(
            Check("llm", False, True, "默认 --via sdk 请设 LLM_API_KEY / LLM_BASE_URL / LLM_MODELS")
        )
        checks.append(Check("agent", False, True, "没有 LLM 配置，自建 agent 无法写策划"))

    required_fail = any(c.required and not c.ok for c in checks)
    return checks, required_fail
