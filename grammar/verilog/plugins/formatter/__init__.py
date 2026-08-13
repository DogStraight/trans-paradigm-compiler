"""Formatter plugin — 结构感知的 Verilog 格式化器

独立于主管线的轻量格式化服务。提供：
  1. 结构边界感知（module/begin/end/ifdef 嵌套追踪）
  2. 声明式品类对齐 + 命令式手写 pass
  3. ifdef/else/endif 宏结构保真

通过 tpc.toml [plugins] enabled 激活。
"""

from __future__ import annotations

import os
from typing import Any

from .engine import FormatterEngine, FormatterPass


# ── 默认品类配置 ──

DEFAULT_CATEGORIES: list[dict[str, Any]] = [
    {
        "name": "port_dir",
        "matcher": {"first_token": ["input", "output", "inout"]},
        "family": "port_dir",
        "align_port_names": True,
        "break_distance": 3,
    },
    {
        "name": "declaration",
        "matcher": {"first_token": ["reg", "wire"]},
        "family": "declaration",
        "break_distance": 3,
    },
    {
        "name": "parameter",
        "matcher": {"first_token": ["parameter", "localparam"]},
        "family": "parameter",
        "break_distance": 3,
    },
    {
        "name": "assignment",
        "matcher": {"first_token": ["assign"]},
        "family": "assignment",
        "break_distance": 3,
    },
    {
        "name": "genvar_integer",
        "matcher": {"first_token": ["genvar", "integer"]},
        "family": "declaration",
        "break_distance": 3,
    },
    {
        "name": "function",
        "matcher": {"first_token": ["function"]},
        "family": "function",
        "break_distance": 3,
    },
    {
        "name": "task",
        "matcher": {"first_token": ["task"]},
        "family": "function",
        "break_distance": 3,
    },
]


def build_engine(categories: list[dict[str, Any]] | None = None) -> FormatterEngine:
    """从配置构建格式化引擎。"""
    from .engine import FormatterEngine, FormatterPass
    from .passes.inst_port import run_inst_port_align

    engine = FormatterEngine()
    categories = categories or DEFAULT_CATEGORIES
    for cat in categories:
        if not cat.get("enabled", True):
            continue
        engine.register(FormatterPass(
            name=cat.get("name", "unknown"),
            kind="category",
            category_cfg={
                "matcher": cat.get("matcher", {}),
                "family": cat.get("family", cat.get("name", "default")),
                "align_port_names": cat.get("align_port_names", False),
                "break_distance": cat.get("break_distance", 3),
            },
        ))
    # 实例端口对齐 pass（命令式，跟在品类 pass 之后）
    engine.register(FormatterPass(
        name="inst_port",
        kind="handler",
        handler=run_inst_port_align,
    ))
    return engine


def format_source(source: str, rules_dir: str, categories: list[dict] | None = None) -> str:
    """一站式格式化入口：lex → 边界扫描 → pass 编排。

    供外部调用（VS Code 插件 / CLI）使用。
    """
    from core.config_registry import ConfigRegistry
    ConfigRegistry.load_all(rules_dir, plugins_dir=os.path.join(rules_dir, "plugins"))

    from lexer import Lexer
    from parser import setup_grammar
    from core.define import GrammarRulesRegister

    rules = setup_grammar(rules_dir, GrammarRulesRegister.get_default())
    lexer = Lexer(rules_dir=rules_dir)

    from .boundary import BoundaryScanner
    scanner = BoundaryScanner(rules, lexer)
    contexts = scanner.scan(source)

    lines = source.split("\n")
    engine = build_engine(categories)
    formatted = engine.run(lines, contexts)
    return "\n".join(formatted)
