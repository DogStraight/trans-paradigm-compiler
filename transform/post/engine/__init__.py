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

from .engine import ConfigDrivenTransform
from .registry import transform_handler, get_handler, TransformContext, SKIP

# ── 内置 handler：expand_typed_port ──
# 将 TypedPortDecl（如 "spi.slave spi_io"）展开为具体的 AnsiInputDecl / AnsiOutputDecl
# 通过 lookup_type_scope 从 scope 类型域中查角色端口列表，按方向分别发射

def _reverse_direction(d: str) -> str:
    """反转端口方向：input ↔ output，inout 不变"""
    if d in ("input", "input_reg"):
        return "output"
    if d in ("output", "output_reg"):
        return "input"
    return d


@transform_handler("expand_typed_port")
def _expand_typed_port(
    node: "core.define.Node",
    root_scope: "analyzer.scope.Scope",
    ctx: TransformContext,
):
    from .primitives import lookup_type_scope, resolve_template, emit as _emit

    # 1. 从 TypedPortDecl 节点取属性
    type_spec = getattr(node, "type_spec", None)
    instance_name = getattr(node, "instance_name", None)
    if type_spec is None or instance_name is None:
        return SKIP

    type_name = getattr(type_spec, "type_name", None) or ""
    role_name = getattr(type_spec, "role_name", None) or ""
    inst_name = getattr(instance_name, "name", None) or getattr(instance_name, "content", None) or ""
    if not type_name or not role_name:
        return SKIP

    # 2. 构建 transform context 供模板解析
    context = {
        "type_spec.type_name": type_name,
        "type_spec.role_name": role_name,
        "instance_name": inst_name,
    }
    key = f"{type_name}.{role_name}"

    # 3. 从 scope 查角色信息
    role_data = lookup_type_scope(root_scope, key, context)
    if not role_data:
        return SKIP

    ports = role_data.get("ports", [])
    if not ports:
        return SKIP

    # 4. 展开端口列表（处理 revert 的反转逻辑）
    # ports 结构（由 capture 从 TypeRole.ports 提取）：
    #   - 正常：{ direction: "input", items: { items: [{name: "miso"}] } }
    #   - revert：{ node_name: "TypeRevertPort", target_role: "master" }
    expanded_ports: list[dict] = []
    for port in ports:
        if not isinstance(port, dict):
            continue

        # 处理 revert：查目标角色的端口，反转方向
        is_revert = port.get("node_name") == "TypeRevertPort"
        if is_revert:
            target_role = port.get("target_role", "")
            if target_role:
                target_key = f"{type_name}.{target_role}"
                target_data = lookup_type_scope(root_scope, target_key, context)
                if target_data:
                    for tp in (target_data.get("ports") or []):
                        if isinstance(tp, dict) and tp.get("direction"):
                            rev_port = dict(tp)
                            rev_port["direction"] = _reverse_direction(rev_port["direction"])
                            expanded_ports.append(rev_port)
            continue

        expanded_ports.append(port)

    # 5. 为每个端口按方向发射节点
    results = []
    for port in expanded_ports:
        direction = port.get("direction", "")

        # 提取端口名（从 items.items[].name）
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

        # 方向 → 节点类型
        if direction in ("input",):
            emit_node = "AnsiInputDecl"
        elif direction in ("output",):
            emit_node = "AnsiOutputDecl"
        elif direction in ("inout",):
            emit_node = "AnsiInoutDecl"
        else:
            emit_node = "AnsiInputDecl"

        # 每个端口名生成一个声明节点
        for port_name in port_names:
            full_name = f"{inst_name}_{port_name}" if inst_name else port_name
            emit_spec = {
                "node": emit_node,
                "direction": direction,
                "sub_node": [
                    {
                        "node": "Declarator",
                        "name": full_name,
                    }
                ],
            }
            decl_node = _emit(emit_spec, context)
            results.append(decl_node)

    return results if results else SKIP


# 导入 core.define 和 analyzer.scope 运行时，避免循环导入
import core.define  # noqa: E402
import analyzer.scope  # noqa: E402


__all__ = [
    "ConfigDrivenTransform",
    "transform_handler",
    "get_handler",
    "TransformContext",
    "SKIP",
]
