"""Transform 引擎 — 配置驱动的 AST 变换管线

设计原则：
  原语优先 — lookup / foreach / emit / replace 覆盖大多数降级场景
  handler 兜底 — 自定义 Python 函数处理原语无法表达的逻辑
  配置驱动 — transform 配置写在规则 TOML 的 [RuleName.transform] 中

用法:
    from transform.post.engine import ConfigDrivenTransform, transform_handler

    # 1. 注册自定义 handler（可选）
    @transform_handler("my_handler")
    def my_handler(node, scope, ctx):
        ...

    # 2. 创建配置驱动变换插件
    transformer = AstTransformer()
    transformer.register(ConfigDrivenTransform(
        rules=grammar_rules,
        ext_dir="grammar/rules_verilog_ext",
    ))
    ast = transformer.transform(ast, scope)
"""

from .core import ConfigDrivenTransform
from .registry import register_primitive, get_primitive, SKIP

# ── 原语：expand_typed_port ──
# 将 TypedPortDecl（如 "spi.slave spi_io"）展开为具体端口声明
# 通过 lookup_type_scope 从 scope 类型域中查角色端口列表，按方向分别发射

def _expand_typed_port(engine, node, config, root_scope):
    from .primitives import lookup_type_scope
    from core.define import Node as _Node

    type_spec = getattr(node, "type_spec", None)
    instance_name = getattr(node, "instance_name", None)
    if type_spec is None or instance_name is None:
        return SKIP

    tn = getattr(type_spec, "type_name", None)
    rn = getattr(type_spec, "role_name", None)
    type_name = getattr(tn, "content", str(tn or ""))
    role_name = getattr(rn, "content", str(rn or ""))
    _name_node = getattr(instance_name, "name", None)
    if isinstance(_name_node, _Node):
        inst_name = getattr(_name_node, "content", "") or ""
    elif isinstance(_name_node, str):
        inst_name = _name_node
    else:
        inst_name = getattr(instance_name, "content", None) or ""
    if not type_name or not role_name:
        return SKIP

    context = {"type_spec.type_name": type_name, "type_spec.role_name": role_name, "instance_name": inst_name}
    role_data = lookup_type_scope(root_scope, f"{type_name}.{role_name}", context)
    if not role_data:
        return SKIP

    ports = role_data.get("ports", [])
    if not ports:
        return SKIP
    if not isinstance(ports, list):
        ports = [ports]

    results = []
    for port in ports:
        direction = port.get("direction", "")
        port_names: list[str] = []
        items = port.get("items", {})
        if isinstance(items, dict):
            inner = items.get("items", [])
            if isinstance(inner, list):
                for decl in inner:
                    if isinstance(decl, dict):
                        n = decl.get("name", "")
                        if n:
                            port_names.append(n)
                    elif isinstance(decl, str):
                        port_names.append(decl)
            elif isinstance(inner, str):
                port_names.append(inner)
        if not port_names:
            continue

        # 符号表中存储的方向直接对应当前角色/模块的 Verilog 关键字：
        #   stored "input"  → 模块侧 input（信号流入模块）
        #   stored "output" → 模块侧 output（信号流出模块）
        #   stored "inout"  → 模块侧 inout
        emit_node = "AnsiInputDecl" if direction in ("input",) else "AnsiOutputDecl" if direction in ("output",) else "AnsiInoutDecl" if direction in ("inout",) else "AnsiInputDecl"
        verilog_dir = direction
        for port_name in port_names:
            full_name = f"{inst_name}_{port_name}" if inst_name else port_name
            decl_node = _Node("Declarator"); decl_node.add_attr("name", full_name)
            decl_list = _Node("DeclaratorList"); decl_list.add_attr("items", [decl_node])
            result_node = _Node(emit_node)
            result_node.add_attr("direction", verilog_dir)
            result_node.add_attr("items", decl_list)
            results.append(result_node)

    return results if results else SKIP


register_primitive("expand_typed_port", _expand_typed_port)


__all__ = [
    "ConfigDrivenTransform",
    "register_primitive",
    "get_primitive",
    "SKIP",
]
