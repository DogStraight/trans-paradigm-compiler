"""symbol.py — 符号声明原语

原语:
    symbol_declare — 从 TOML [RuleName.analyzer] symbol 配置声明符号
    capture_hook   — 运行注册的 capture 后处理器（由 symbol.capture_hooks 触发）

配置格式:
    [RuleName.analyzer]
    symbol = { kind = "module", name_attr = "module_name" }
    symbol = {
        kind = "role",
        name_attr = "role_name",
        capture = { ports = "ports" },
        capture_hooks = ["resolve_revert"],
    }

capture 配置:
    将节点属性提取到符号的 attrs 字典中。
    format: capture = { attr_name = "source_path", ... }
    例如: capture = { ports = "ports" } → 将 node.ports 内容存入 sym.attrs["ports"]
"""

from typing import Any, Optional, Callable
from core.define import Node
from .registry import analyzer_primitive

# ── Capture 后处理器注册中心 ──
# 语言特定的 capture 后处理通过此系统注册，不硬编码在原语中。
# 由 TOML 中 [RuleName.analyzer] symbol.capture_hooks = ["resolve_revert"] 触发

_capture_hooks: dict[str, Callable] = {}


def register_capture_hook(name: str) -> Callable:
    """装饰器：注册一个 capture 后处理器

    Hook 签名:
        def hook(node, sym_rule, scope, name, attrs) -> dict:
            # 修改 attrs 并返回
            return attrs
    """
    def decorator(fn: Callable) -> Callable:
        _capture_hooks[name] = fn
        return fn
    return decorator


# ── 原语: symbol_declare ──


@analyzer_primitive("symbol_declare")
def symbol_declare(analyzer, node: Node, config: dict) -> None:
    """声明符号

    根据 TOML symbol 配置从节点提取名称、捕获属性、注册符号到当前作用域。
    支持:
        - 单名声明（name_attr 指向单个值）
        - 多项声明（name_attr 指向列表，如 items）
        - capture 属性提取（纯 JSON 可序列化）
        - capture_hooks 后处理
    """
    sym_meta = config.get("symbol")
    if not sym_meta:
        return

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
            analyzer._errors.append(f"重复声明 '{name}' 在作用域 '{current_scope.name}'")
            continue

        # 提取 capture 数据
        attrs: dict = _build_capture_attrs(node, capture)

        # capture 后处理器
        for hook_name in hooks:
            hook = _capture_hooks.get(hook_name)
            if hook:
                attrs = hook(node, sym_meta, current_scope, name, attrs) or attrs

        sym = current_scope.declare(name=name, kind=kind, decl_node=node, attrs=attrs)
        analyzer._all_symbols.append(sym)


# ── 原语: identifier_resolve ──


@analyzer_primitive("identifier_resolve")
def identifier_resolve(analyzer, node: Node, config: dict) -> None:
    """解析标识符引用

    根据 TOML [RuleName.analyzer] identifier_ref 配置，
    沿作用域链查找标识符对应的符号，附加 _symbol_ref 引用。

    配置:
        identifier_ref = true       — 从 content/name 属性取引用名
        identifier_ref = "attr"     — 从指定属性取引用名（如 type_name）
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
        # 从指定属性提取引用名（如 TypedTypeSpec 的 type_name）
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
        # 指定属性名时：找不到符号则记录未解析引用
        msg = f"未解析的{iref}引用: '{name}' (节点: {node.node_name})"
        analyzer._unresolved_refs.append(f"{node.node_name}.{iref}: '{name}'")
        print(f"[analyzer] WARN {msg}")


# ============================================================
# 内部辅助函数
# ============================================================


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
    names: list[str] = []
    for val in _walk_path(node, name_attr):
        name = _resolve_name_value(val)
        if name:
            names.append(name)
    if not names:
        # 兜底：属性指向列表，从各元素提取名称
        val = getattr(node, name_attr.split(".")[0], None)
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


def _resolve_name_value(val: Any) -> Optional[str]:
    """将值解析为符号名字符串"""
    if val is None:
        return None
    if isinstance(val, Node):
        return getattr(val, "content", getattr(val, "value", None))
    if isinstance(val, str):
        return val
    return str(val) if val is not None else None
