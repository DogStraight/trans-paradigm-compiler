"""symbol.py — 符号声明原语

原语:
    symbol_declare — 从 TOML [RuleName.analyzer] symbol 配置声明符号

配置格式:
    [RuleName.analyzer]
    symbol = { kind = "module", name_attr = "module_name" }
    symbol = {
        kind = "role",
        name_attr = "role_name",
        capture = { ports = "ports" },
        capture_hooks = ["resolve_invert"],
    }

capture 配置:
    将节点属性提取到符号的 attrs 字典中。
    format: capture = { attr_name = "source_path", ... }
    例如: capture = { ports = "ports" } → 将 node.ports 内容存入 sym.attrs["ports"]
Doc: analyzer/semantic_checks.md（符号收集原语）
"""

from typing import Any, Callable
from core.define import Node
from analyzer.primitives.registry import register

# ── Capture 后处理器中心（目前未使用，保留扩展点）──
_capture_hooks: dict[str, Callable] = {}


# ── 原语: symbol_declare ──


@register("symbol_declare")
def symbol_declare(analyzer, node: Node, config: dict) -> None:
    """声明符号

    根据 TOML symbol 配置从节点提取名称、捕获属性、注册符号到当前作用域。
    支持: 单名 / 多项声明 / capture 属性提取 / capture_hooks 后处理

    无显式 symbol 时从 scope 配置推断（声明规则通常 scope 与 symbol 的
    kind/name_attr 一致——如 FuncDecl 的 function/func_name、TaskDecl 的
    task/task_name）：scope 带 name_attr 即视为"声明符号 + 进入作用域"，
    避免每个声明规则重复写两份几乎相同的配置。
    """
    sym_meta = config.get("symbol")
    if not sym_meta:
        scope_meta = config.get("scope")
        if not isinstance(scope_meta, dict) or not scope_meta.get("name_attr"):
            return
        sym_meta = {
            "kind": scope_meta.get("kind", "unknown"),
            "name_attr": scope_meta.get("name_attr"),
        }

    current_scope = analyzer._current_scope
    assert current_scope is not None

    kind: str = sym_meta.get("kind", "unknown")
    name_attr = sym_meta.get("name_attr")
    if not name_attr:
        return

    capture = sym_meta.get("capture", {})
    hooks = sym_meta.get("capture_hooks", [])
    if isinstance(hooks, str):
        hooks = [hooks]

    names = _extract_names(analyzer, node, name_attr)
    for name in names:
        if not name:
            continue

        if name in current_scope.symbols:
            # 允许重名作用域（由 [analyzer.scope] allow_duplicate 规则字段声明，如
            # generate 条件生成分支互斥——elaboration 只展开一个，各分支同名声明
            # 合法）：合并保留首例不报错。
            if not current_scope.allow_duplicate:
                analyzer._context.report(
                    f"重复声明 '{name}' 在作用域 '{current_scope.name}'", code="E001"
                )
            continue

        attrs: dict = _build_capture_attrs(node, capture)

        for hook_name in hooks:
            hook = _capture_hooks.get(hook_name)
            if hook:
                attrs = hook(node, sym_meta, current_scope, name, attrs) or attrs

        sym = current_scope.declare(name=name, kind=kind, decl_node=node, attrs=attrs)
        analyzer._all_symbols.append(sym)


# ── 内部辅助函数 ──


def _build_capture_attrs(node: Node, capture: dict) -> dict:
    """从节点提取 capture 配置指定的属性值

    返回纯 JSON 可序列化的字典。
    """
    attrs: dict = {}
    if not capture:
        return attrs

    for attr_name, source_path in capture.items():
        captured = list(_walk_path(node, source_path))
        if captured:
            values = [_capture_val(v) for v in captured]
            values = [v for v in values if v is not None]
            if values:
                attrs[attr_name] = values if len(values) > 1 else values[0]

    return attrs


def _capture_val(val: Any) -> Any:
    """将 Node 属性递归提取为 JSON 可序列化的值"""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, Node):
        # 优先取主要值（content/name/value）
        for p in ("content", "name", "value"):
            pv = getattr(val, p, None)
            if pv is not None and isinstance(pv, str):
                return pv
        # 否则递归提取所有非私有属性
        d: dict = {}
        for sub_attr in vars(val):
            if sub_attr.startswith("_"):
                continue
            sv = _capture_val(getattr(val, sub_attr))
            if sv is not None:
                d[sub_attr] = sv
        return d if d else None
    if isinstance(val, list):
        items = [_capture_val(v) for v in val]
        items = [v for v in items if v is not None]
        return items if items else None
    return str(val)


def _walk_path(node: Node, path: str) -> Any:
    """沿点号路径遍历节点属性，逐层 yield。

    遇到 list → 展开每个元素继续遍历；
    遇到 Node → getattr；
    其他类型 → 终止。
    """
    parts = path.split(".")
    stack: list = [(node, 0)]
    while stack:
        val, idx = stack.pop()
        if idx >= len(parts):
            yield val
            continue
        p = parts[idx]
        if isinstance(val, Node):
            child = getattr(val, p, None)
            if child is not None:
                stack.append((child, idx + 1))
        elif isinstance(val, list):
            for item in reversed(val):
                stack.append((item, idx))
        else:
            return


def _extract_names(analyzer, node: Node, name_attr: str) -> list[str]:
    """从节点属性中提取符号名列表，支持列表属性"""
    del analyzer  # 原语注册协议签名参数，本函数不消费
    names: list[str] = []
    for val in _walk_path(node, name_attr):
        name = _resolve_name_value(val)
        if name:
            names.append(name)
    if not names:
        # 兜底：属性指向列表，从各元素提取名称。
        # 支持两种容器形态：
        #   1. 裸 list（node.items = [Node, ...]）
        #   2. 列表容器节点（node.items = DeclaratorList，其 items 字段是
        #      list——Declarator 等声明列表在 parser 端是 Node 包装，
        #      name_attr = "items.name" 的 items 实际是容器 Node）
        val = getattr(node, name_attr.split(".")[0], None)
        if isinstance(val, Node):
            container_items = getattr(val, "items", None)
            if isinstance(container_items, list):
                val = container_items
        if isinstance(val, list):
            fallback_attrs = ["param_name", "name"]
            for item in val:
                if isinstance(item, Node):
                    for attr_name in fallback_attrs:
                        n = getattr(item, attr_name, None)
                        if n:
                            name = _resolve_name_value(n)
                            if name:
                                names.append(name)
                                break
    return names


def _resolve_name_value(val: Any) -> str | None:
    """将值解析为符号名字符串"""
    if val is None:
        return None
    if isinstance(val, Node):
        return getattr(val, "content", getattr(val, "value", None))
    if isinstance(val, str):
        return val
    return str(val) if val is not None else None
