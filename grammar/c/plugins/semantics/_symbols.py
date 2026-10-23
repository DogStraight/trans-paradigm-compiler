"""_symbols.py — C 符号收集的**引擎装配面**（analyzer handler 入口）。

⚠ 本文件只做注册与装配：`@register("c_symbol_collect")` + postpass 入口 +
raw 校验查询桥（`_raw_bridge`，其导入即注册，见下）。查询/产物逻辑在 `_api.py` /
`_p4_query.py`（**无注册副作用**，测试与消费方直接按包路径 import，避免二次 exec 重复注册）。
Doc: grammar/c/README.md（符号收集产物：形状 / 分期语义 / 默认偏置）
"""
from __future__ import annotations

from typing import Any

from core.define import Node
from analyzer.primitives.registry import register

from grammar.c.plugins.semantics._api import (
    collect_declarator_site,
    collect_named_site,
    build_product,
)


@register("c_symbol_collect")
def c_symbol_collect(analyzer: Any, node: Node, config: dict) -> None:
    """声明式符号收集原语（`[Rule.analyzer.c_symbol_collect]` 键即触发）。

    ⚠ 原语收到的是**规则级 analyzer 配置**，站点参数在自己的键下（与
    `checks/semantic_check/_name_check.py::check_name_call` 同约定，见
    `AnalysisTraversal._custom_primitive_names` 的"键名即原语名"），故先取子表再分派。
    站点：`declarator`（声明符位）/ `named`（属性上的名）；站点与提取路径全部由语言包
    TOML 给出，引擎侧与组件侧都不含 C 语法知识（见 `_api.py`）。
    """
    self_cfg = config.get("c_symbol_collect") or {}
    site = self_cfg.get("site", "")
    if site == "declarator":
        collect_declarator_site(analyzer, node, self_cfg)
    elif site == "named":
        collect_named_site(analyzer, node, self_cfg)


def run_symbol_product(analyzer: Any, context: Any) -> None:
    """postpass：把 analyze 期符号表物化进 `context.extra[PRODUCT_KEY]`（只写 context）。"""
    build_product(analyzer, context)
