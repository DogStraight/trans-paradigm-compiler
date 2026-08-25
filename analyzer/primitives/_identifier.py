"""identifier.py — 标识符解析原语

原语:
    identifier_resolve — 沿作用域链查找标识符对应的符号，附加 _symbol_ref 引用

配置格式:
    [RuleName.analyzer]
    identifier_ref = true       — 从 content/name 属性取引用名
    identifier_ref = "attr"     — 从指定属性取引用名（如 type_name）
Doc: docs/semantic_checks.md（标识符引用解析原语）
"""

from core.define import Node
from analyzer.primitives.registry import register


@register("identifier_resolve")
def identifier_resolve(analyzer, node: Node, config: dict) -> None:
    """解析标识符引用

    根据 TOML [RuleName.analyzer] identifier_ref 配置，
    沿作用域链查找标识符对应的符号，附加 _symbol_ref 引用。
    """
    iref = config.get("identifier_ref")
    if not iref:
        return

    current_scope = analyzer._current_scope
    assert current_scope is not None

    # 跳过作用域定义名自身的 Identifier（如模块名、函数名）
    if id(node) in analyzer._scope_name_node_ids:
        return

    if isinstance(iref, str):
        name = getattr(node, iref, None)
        if isinstance(name, Node):
            name = getattr(name, "content", str(name))
    else:
        name = getattr(node, "content", None) or getattr(node, "name", None)

    if not name:
        return

    sym = current_scope.resolve(name)
    if sym is not None:
        node.add_attr("_symbol_ref", sym)
    elif isinstance(iref, str):
        analyzer._context.report(f"未解析的{iref}引用: '{name}'", code="W001", level="warning")
