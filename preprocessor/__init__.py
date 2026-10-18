"""Preprocessor — TOML-driven macro expansion and reversal（语言无关）。

Architecture:
    Source → Preprocessor (expand) → Lexer → Parser → ... → Renderer → Reverse
Doc: preprocessor/README.md
"""

from core.config_registry import config_refs_for
from . import _expand, _reverse
from ._expand import scan_directives, expand_tokens, enumerate_conditions
from ._reverse import protect_and_reverse, restore_condition_blocks

__all__ = [
    "scan_directives",
    "expand_tokens",
    "enumerate_conditions",
    "protect_and_reverse",
    "restore_condition_blocks",
    "get_config_refs",
    "scan_diagnostics",
    "_expand",
    "_reverse",
]


def scan_diagnostics(
    source: str,
    rules_dir: str,
    *,
    source_path: str | None = None,
    include_dirs: list[str] | None = None,
) -> list[dict]:
    """预处理问题诊断（**不抛异常**；给 CLI 两条路径共用）。

    目前 = include 问题（缺文件/循环/深度超限）+ 条件指令问题（`#if`/`#elif`
    表达式求值错误、条件块配对错误；仅声明 `[condition]` 的语言包产生）——
    按语言包策略产生：C 包声明 `error` ⇒ 有诊断；verilog 默认 `warn` / 未声明
    条件面 ⇒ 返回空（保持既有行为）。返回 `[{kind, message, line, column}]`；
    用户可见面（打印/退出码）由调用方负责。

    `ConfigError` 转**受控诊断**（`kind="directive"`）：指令处理器的 fail-fast
    （如未闭合的 `#define` 形参表）冒泡到 CLI 会打成 traceback，与本文档"不抛
    异常"契约相悖；语言配置错误同样是 ConfigError——统一转受控报文（rc=1、
    点名原因，仍非静默）。
    """
    from core.errors import ConfigError

    diags: list[dict] = []
    try:
        scan_directives(
            source,
            rules_dir,
            source_path=source_path,
            search_dirs=include_dirs,
            out_diags=diags,
        )
    except ConfigError as exc:
        diags.append({"kind": "directive", "message": str(exc)})
    return [
        d
        for d in diags
        if d.get("kind")
        in (
            "missing",
            "cycle",
            "depth",
            "condition",
            "condition-balance",
            "directive",
        )
    ]


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    return config_refs_for(__name__)
