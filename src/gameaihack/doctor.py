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
    py_ok = sys.version_info >= (3, 11)
    checks.append(
        Check(
            "python>=3.11",
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

    for exe, req, why in (
        ("apktool", False, "解码 Manifest/resources"),
        ("jadx", False, "Java 反编译"),
        ("Il2CppDumper", False, "IL2CPP dummy dll"),
        ("adb", False, "deep 模式 pull 缓存"),
        ("frida", False, "deep 明文 dump（可选）"),
        ("docker", False, "推荐分发方式"),
        ("gplaydl", False, "按包名从 Play 下载（需 gplaydl link）"),
    ):
        path = shutil.which(exe)
        checks.append(Check(exe, bool(path), req, path or why))

    from gameaihack.dsh_agent import dsh_argv

    dsh = dsh_argv()
    if dsh:
        checks.append(Check("dsh", True, True, " ".join(dsh)))
    else:
        checks.append(
            Check(
                "dsh",
                False,
                True,
                "必须安装 @deepseek-ai/dsh（Node 22.19+/24，不是 23）。见 README",
            )
        )

    from gameaihack.llm import resolve_llm

    llm = resolve_llm()
    if llm:
        checks.append(Check("llm", True, True, f"{llm.source} · model {llm.model} · {llm.base_url}"))
    else:
        checks.append(Check("llm", False, True, "必须设 LLM_API_KEY / LLM_BASE_URL / LLM_MODELS"))

    required_fail = any(c.required and not c.ok for c in checks)
    return checks, required_fail
