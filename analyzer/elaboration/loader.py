"""loader.py — 精化能力的读取点（语言包 `[capabilities] elaborator`）。

与 `preprocessor/macro_policy.py::load_macro_policy` **同款**：按 **rules_dir**
作用域查找（只有该语言包 `plugins/` 下的组件才有资格应答 → 同进程切语言不串用）；
未声明 → `None`（引擎降级）；声明非法 → fail-fast（`parse_spec`）。

能力入口（`file.py:fn`）返回能力 API 面（表）：`{"items": [...], "solvers": {...}}`。

Doc: analyzer/elaboration/README.md
"""
from __future__ import annotations

from analyzer.elaboration.contract import ElaboratorSpec, parse_spec

# 能力名（语言包 `[capabilities]` 段声明；见 core/component_protocol.md）
CAPABILITY_NAME = "elaborator"


def load_elaborator_spec(rules_dir: str) -> ElaboratorSpec | None:
    """取该语言包的精化能力面（未声明 → None = 降级）。"""
    from core.plugin_loader import get_capability_in

    entry = get_capability_in(CAPABILITY_NAME, rules_dir)
    if entry is None:
        return None
    return parse_spec(entry())
