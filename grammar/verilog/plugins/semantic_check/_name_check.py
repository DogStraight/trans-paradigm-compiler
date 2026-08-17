"""_name_check.py — 通用名称检查原语（semantic_check 插件）

原语:
    check_name_call — 解析名称引用（如 task/function 调用名），沿作用域链
    查找声明符号；未找到时暂存、遍历结束后统一核对（支持前向引用——
    单遍遍历时声明可能在调用后方）。

与内置 identifier_resolve 的区别：
    identifier_resolve 是通用标识符解析（Identifier 节点 identifier_ref=true
    只 attach 不报，避免隐式 net 误报）；check_name_call 是插件暴露的
    "名称调用检查"pass，供规则通过 primitives 配置触发，未解析报 W002。

配置格式（TOML）:
    [RuleName.analyzer]
    primitives = ["check_name_call"]
    check_name_call = { name_attr = "callee" }

前置：声明规则（TaskDecl/FuncDecl）已配置 symbol_declare（名字入符号表），
     调用点沿作用域链可解析。
"""

from core.define import Node
from analyzer.primitives.registry import register


@register("check_name_call")
def check_name_call(analyzer, node: Node, config: dict) -> None:
    """解析名称引用；未定义暂存，遍历后统一核对报 W002。"""
    self_cfg = config.get("check_name_call") or {}
    name_attr = self_cfg.get("name_attr", "callee")

    name = getattr(node, name_attr, None)
    if isinstance(name, Node):
        name = getattr(name, "content", None) or str(name)
    if not name:
        return

    scope = analyzer._current_scope
    sym = scope.resolve(name)
    if sym is not None:
        node.add_attr("_symbol_ref", sym)
    else:
        # 暂存：单遍遍历时声明可能在调用后方（前向引用），
        # 遍历结束后符号表已满，用同一 scope 对象重新核对。
        analyzer._pending_name_refs.append((scope, name, node))
