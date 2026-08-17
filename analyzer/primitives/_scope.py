"""scope.py — 作用域管理原语

原语:
    scope_enter — 从 TOML [RuleName.analyzer] scope 配置进入新作用域
    scope_exit  — 退出当前作用域

配置格式:
    [RuleName.analyzer]
    scope = { name_attr = "module_name", kind = "module" }
    scope = { kind = "type", name_attr = "type_name" }
    scope = { kind = "generate", allow_duplicate = true }  # 允许同名声明
"""

from core.define import Node
from analyzer.scope import Scope
from analyzer.primitives.registry import register


@register("scope_enter")
def scope_enter(analyzer, node: Node, config: dict) -> None:
    """进入新作用域

    根据 TOML scope 配置创建子作用域并设置为当前作用域。
    scope 配置:
        name_attr: 从节点哪个属性取作用域名（如 "module_name"）
        kind:      作用域种类（如 "module"、"type"、"block"）
    """
    scope_meta = config.get("scope")
    if not scope_meta:
        return

    current_scope = analyzer._current_scope
    assert current_scope is not None

    name_attr = scope_meta.get("name_attr")
    if name_attr:
        name_val = getattr(node, name_attr, None)
        if isinstance(name_val, Node):
            scope_name = getattr(name_val, "content", node.node_name)
            analyzer._scope_name_node_ids.add(id(name_val))
        elif name_val is not None:
            scope_name = str(name_val)
        else:
            scope_name = node.node_name
    else:
        scope_name = node.node_name

    kind = scope_meta.get("kind", "block")
    allow_duplicate = bool(scope_meta.get("allow_duplicate", False))
    new_scope = Scope(
        name=scope_name,
        kind=kind,
        parent=current_scope,
        allow_duplicate=allow_duplicate,
    )
    current_scope.children.append(new_scope)
    analyzer._current_scope = new_scope


@register("scope_exit")
def scope_exit(analyzer, node: Node, config: dict) -> None:
    """退出当前作用域

    恢复父作用域为当前作用域。
    仅当 TOML 中存在 scope 配置时执行。
    """
    scope_meta = config.get("scope")
    if not scope_meta:
        return

    assert analyzer._current_scope is not None
    parent = analyzer._current_scope.parent
    assert parent is not None, "scope_exit: 无可退出的父作用域"
    analyzer._current_scope = parent
