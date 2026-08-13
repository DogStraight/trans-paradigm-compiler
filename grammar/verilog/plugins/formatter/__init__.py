"""Formatter plugin — 结构感知的 Verilog 格式化器

独立于主管线的轻量格式化服务。提供：
  1. 结构边界感知（module/begin/end/ifdef 嵌套追踪）
  2. 声明式品类对齐 + 命令式手写 pass
  3. ifdef/else/endif 宏结构保真

通过 tpc.toml [plugins] enabled 激活。
"""

from __future__ import annotations

import os
import re
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


def _load_categories_from_config() -> list[dict] | None:
    """从 ConfigRegistry 读品类配置（语言包 tpc.toml 的 [[formatter.categories]]）。

    未加载 / 无配置时返回 None（调用方 fallback 到代码内默认值）。
    """
    try:
        from core.config_registry import ConfigRegistry
        cfg = ConfigRegistry.get("formatter.categories")
        if isinstance(cfg, list) and cfg:
            return cfg
    except Exception:
        pass
    return None


def build_engine(categories: list[dict[str, Any]] | None = None) -> FormatterEngine:
    """从配置构建格式化引擎。"""
    from .engine import FormatterEngine, FormatterPass
    from .passes.indent import run_indent_pass
    from .passes.ifdef import run_ifdef_pass
    from .passes.inst_port import run_inst_port_align
    from .passes.wrap import run_wrap_pass
    from .style import load_style

    style = load_style()  # indent_width / max_line_width（配置驱动）
    iw = style.get("indent_width", 4)
    mw = style.get("max_line_width", 100)

    engine = FormatterEngine()
    # 缩进重排 pass（最前：先定缩进，品类/端口对齐再基于新缩进重组行）
    engine.register(FormatterPass(
        name="indent",
        kind="handler",
        handler=lambda lines, ctxs: run_indent_pass(
            lines, ctxs, indent_width=iw
        ),
    ))
    # 条件编译块内容缩进 pass（紧跟单语句头的 ifdef 块内容继承悬挂）
    engine.register(FormatterPass(
        name="ifdef",
        kind="handler",
        handler=lambda lines, ctxs: run_ifdef_pass(
            lines, ctxs, indent_width=iw
        ),
    ))
    if categories is None:
        # 品类定义外部化到语言包 tpc.toml（配置驱动）；未加载时 fallback 默认
        categories = _load_categories_from_config() or DEFAULT_CATEGORIES
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
    # 宽度折行 pass（最后：品类/端口对齐定稿后，超宽行折行；续行继承语句头 +1）
    engine.register(FormatterPass(
        name="wrap",
        kind="handler",
        handler=lambda lines, ctxs: run_wrap_pass(
            lines, ctxs, max_width=mw, indent_width=iw
        ),
    ))
    return engine


# 参数化实例化尾行：`...name(expr)) inst_name (`（参数列表关闭 `)` + 实例名 + 端口开 `(`）
_INST_TAIL_RE = re.compile(r"^(.*)\)\s+(\w+)\s*\($")


def split_inst_tail_lines(lines: list[str]) -> list[str]:
    """拆参数化实例化粘连行：`...) inst_name (` → `...` + `) inst_name (`。

    渲染器常把参数列表关闭 `)` 与实例名、端口开 `(` 粘连成一行，如
    `.STACKADDR(STACKADDR)) picorv32_core (`。ref 风格是参数行 + `) inst_name (` 独立行。

    识别：行尾 `) inst_name (` 且其前部分以 `)` 结尾（即参数关闭 + 参数列表关闭的
    `))` 形态，head 为括号平衡的完整最后一个参数）。只加换行，不改 token。
    """
    out: list[str] = []
    for line in lines:
        s = line.rstrip()
        m = _INST_TAIL_RE.match(s)
        if m:
            head = m.group(1).rstrip()
            # head 须以 `)` 结尾（行内 `))`，参数关闭 + 参数列表关闭相邻），
            # 且为 `.name(...)` 参数形态；括号平衡（完整参数）才拆
            if head.endswith(")") and "." in head and _balanced_parens(head):
                out.append(head)
                out.append(s[len(head):])
                continue
        out.append(line)
    return out


def _balanced_parens(s: str) -> bool:
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def split_port_close_lines(
    lines: list[str], categories: list[dict] | None = None
) -> list[str]:
    """拆模块端口尾行：`output name );` → `output name` + `);`（ref picorv32_wb 风格）。

    渲染器常把模块端口关闭符 `);` 粘连到最后一个端口行（如 `output mem_instr );`），
    且该行顶格。这里按 port_dir 品类 matcher（input/output/inout）识别端口尾行，
    把 `);` 拆为独立行（indent 按 port_list_end 对齐 0 级），端口行本身交给后续
    indent/port_dir 对齐统一缩进。只加换行，不改 token。
    """
    if categories is None:
        categories = _load_categories_from_config() or DEFAULT_CATEGORIES
    port_tokens: set[str] = set()
    for cat in categories:
        # 只认端口方向品类（port_dir），防误拆 assignment/declaration 等
        # （如 `assign z = `MIN(x, y);` 行尾也含 `);`，但 first_token 是 assign）
        if cat.get("family") != "port_dir":
            continue
        first = cat.get("matcher", {}).get("first_token")
        if isinstance(first, str):
            port_tokens.add(first)
        elif isinstance(first, list):
            port_tokens.update(first)
    if not port_tokens:
        return list(lines)
    out: list[str] = []
    for line in lines:
        s = line.rstrip()
        if s.endswith(");") and s.strip():
            first = s.lstrip().split(None, 1)[0]
            if first in port_tokens:
                out.append(s[:-2].rstrip())
                out.append(");")
                continue
        out.append(line)
    return out


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

    # 先拆粘连行（端口尾行 `name );` + 参数化实例化尾行 `...); inst (`），
    # 再扫描/跑 pass，避免 contexts 错位
    lines = split_port_close_lines(source.split("\n"), categories)
    lines = split_inst_tail_lines(lines)
    split_source = "\n".join(lines)

    from .boundary import BoundaryScanner
    scanner = BoundaryScanner(rules, lexer)
    contexts = scanner.scan(split_source)

    engine = build_engine(categories)
    formatted = engine.run(lines, contexts)
    # 清理行尾尾随空格（对齐产生的冗余；ref 0 行尾随）
    return "\n".join(l.rstrip() for l in formatted)
