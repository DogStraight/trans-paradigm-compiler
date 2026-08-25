"""Renderer — AST + 布局规则驱动的代码生成器

只包含 DSL 原语（text/ref/join/group/line/indent/opt），
所有语言特定知识来自 TOML 布局规则。

模块结构:
    renderer.py          — 主类 Renderer（轻量 orchestrator）
    primitives/          — 每个 DSL 原语一个文件
        text.py          — text 原语
        ref.py           — ref 原语
        join.py          — join 原语
        group.py         — group 原语
        line.py          — line 原语
        indent.py        — indent 原语
        opt.py           — opt 原语
        soft_break.py    — soft / break 原语
        align.py         — align 原语（绝对列对齐，ADR-0006 阶段 2）
        fill.py          — fill 原语（流式折行，ADR-0006 阶段 2）
        line_suffix.py   — line_suffix 原语（行尾锚定，ADR-0006 阶段 2）
        registry.py      — 原语注册表
    node_renderer.py     — 节点级渲染（_render_node / _render_inline / _render_body）
    loader.py            — TOML 布局规则 / 风格 / 配置加载
    doc.py               — Doc IR 类型 + layout 算法（Wadler-Leijen 模型）
"""

from .renderer import Renderer
from transform.normalizer import normalize_ast

__all__ = ["Renderer", "normalize_ast", "get_config_refs"]


from core.config_registry import _CONFIG_DECLARATIONS


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    prefix = __name__ + "."
    return {k: var for k, entries in _CONFIG_DECLARATIONS.items() for mod, var in entries if mod.startswith(prefix)}
