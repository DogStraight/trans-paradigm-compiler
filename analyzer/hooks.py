"""analyzer/hooks.py — Verilog 专用的 capture 后处理器

capture hook 在符号声明（symbol_declare）的 capture 数据提取后执行，
用于做语言专用的数据变换，如嵌套类型引用展开。

注册方式：
    @register_capture_hook("hook_name")
    def my_hook(node, sym_rule, scope, name, attrs) -> dict:
        ...
        return attrs

使用方式（TOML）：
    [RuleName.analyzer]
    symbol = { ..., capture_hooks = ["resolve_nested"] }
"""

from copy import deepcopy
from core.config_registry import config as _config
from .primitives import register_capture_hook


# ── 嵌套类型解析调用栈 ──
# 检测循环引用：(type_name, role_name) 对入栈，重复则报错跳过。
# 这是模块级状态，因为 capture hook 的 scope 参数来自不同类型作用域。
_nested_resolve_stack: list[tuple[str, str]] = []


@register_capture_hook("resolve_nested")
def resolve_nested(node, sym_rule, scope, name, attrs):
    """展开嵌套类型引用：将 TypeNestedPort 替换为实际端口

    当 TypeRole 的 capture 遇到 TypeNestedPort 条目时：
        { type_spec: { type_name: "axis", role_name: "master" },
          instance_name: "data" }

    查找类型作用域 axis → 角色符号 master → 其 ports，
    复制每个端口，将 name 前缀改为 "data_"，替换原条目。

    循环引用检测：通过 _nested_resolve_stack 维护 (type, role) 对，
    重复入栈时判为循环引用，跳过展开并输出错误信息。

    Args:
        node:     当前 AST 节点（TypeRole）
        sym_rule: symbol 配置字典
        scope:    当前作用域（类型作用域）
        name:     角色名称
        attrs:    已提取的 capture 属性字典
    Returns:
        修改后的 attrs
    """
    if "ports" not in attrs or not isinstance(attrs["ports"], list):
        return attrs

    resolved = []
    for port in attrs["ports"]:
        if isinstance(port, dict) and "type_spec" in port:
            resolved.extend(
                _resolve_one_nested(port, scope)
            )
        else:
            resolved.append(port)

    attrs["ports"] = resolved
    return attrs


def _get_rev_map() -> dict:
    """从配置读取方向反转映射表（语言专用数据在 TOML 中）"""
    try:
        d = _config.get("analyzer.direction")
        return d.get("revert_map", {})
    except (KeyError, RuntimeError):
        return {}


def _find_type_scope(scope, type_name: str):
    """沿作用域链向上查找 type 子作用域"""
    current = scope
    while current is not None:
        ts = current.find_child_scope(type_name, "type")
        if ts is not None:
            return ts
        current = current.parent
    return None


def _resolve_one_nested(port: dict, scope) -> list[dict]:
    """解析单个嵌套引用条目，返回展开后的端口列表"""
    type_spec = port["type_spec"]
    type_name = type_spec.get("type_name", "")
    role_name = type_spec.get("role_name", "")
    inst_name = port.get("instance_name", "")

    if not type_name or not role_name:
        return [port]

    # 循环引用检测
    pair = (type_name, role_name)
    if pair in _nested_resolve_stack:
        print(f"[analyzer] ERROR 循环嵌套引用: "
              f"{' → '.join(f'{t}.{r}' for t, r in _nested_resolve_stack + [pair])}")
        return [port]

    # 从当前作用域沿父链到根，查找类型子作用域
    # 嵌套类型可能引用同级或全局的类型（不在当前 scope 的子域中）
    type_scope = _find_type_scope(scope, type_name)
    if type_scope is None:
        print(f"[analyzer] WARN 找不到类型 '{type_name}' 的作用域")
        return [port]

    # 在类型作用域中查找角色符号
    role_sym = type_scope.resolve(role_name)
    if role_sym is None or "ports" not in role_sym.attrs:
        print(f"[analyzer] WARN 类型 '{type_name}' 中找不到角色 '{role_name}'")
        return [port]

    src_ports = role_sym.attrs["ports"]

    # 入栈后递归解析嵌套引用
    _nested_resolve_stack.append(pair)
    try:
        return _expand_ports(src_ports, type_scope, inst_name)
    finally:
        _nested_resolve_stack.pop()


def _expand_ports(src_ports: list, type_scope, inst_name: str) -> list[dict]:
    """展开端口列表，处理 revert/嵌套引用，前缀 instance_name

    Args:
        src_ports:   源端口列表（可能含 revert/嵌套引用）
        type_scope:  类型作用域（用于查找 revert 目标角色）
        inst_name:   实例名前缀
    """
    results = []
    for src_port in src_ports:
        if not isinstance(src_port, dict):
            continue
        # revert → 在 type_scope 中查找目标角色，反转方向
        if "target_role" in src_port:
            rev_results = _resolve_revert(src_port, type_scope, inst_name)
            results.extend(rev_results)
        # 嵌套引用 → 递归解析
        elif "type_spec" in src_port:
            nested_results = _resolve_one_nested(src_port, type_scope)
            for np in nested_results:
                _prefix_port_name(np, inst_name)
                results.append(np)
        else:
            new_port = deepcopy(src_port)
            _prefix_port_name(new_port, inst_name)
            results.append(new_port)
    return results


def _prefix_port_name(port: dict, prefix: str) -> None:
    """递归为端口的 name 字段添加前缀

    处理两种结构：
    - 扁平: { name: "tvalid", ... }
    - 嵌套: { items: { items: [{ name: "tvalid" }, ...] } }
    """
    if "name" in port and isinstance(port["name"], str):
        port["name"] = f"{prefix}_{port['name']}"
    if "items" in port and isinstance(port["items"], dict):
        inner = port["items"].get("items", [])
        if isinstance(inner, list):
            for item in inner:
                _prefix_port_name(item, prefix)


def _resolve_revert(port: dict, type_scope, parent_inst: str) -> list[dict]:
    """内联解析 revert 引用：在 type_scope 中查找目标角色，反转方向

    port 格式: { target_role = "master", node_name = "TypeRevertPort" }
    """
    target_role = port.get("target_role", "")
    if not target_role:
        return [port]

    role_sym = type_scope.resolve(target_role)
    if role_sym is None or "ports" not in role_sym.attrs:
        return [port]

    # 反转方向映射表（从 _analyzer.toml 的 [direction] revert_map 读取）
    _REV_MAP = _get_rev_map()

    results = []
    for src_port in role_sym.attrs["ports"]:
        if not isinstance(src_port, dict):
            continue
        # 目标角色的端口也可能包含 revert/嵌套 → 递归
        if "target_role" in src_port:
            sub_results = _resolve_revert(src_port, type_scope, parent_inst)
            results.extend(sub_results)
        elif "type_spec" in src_port:
            sub_results = _resolve_one_nested(src_port, type_scope)
            for np in sub_results:
                _prefix_port_name(np, parent_inst)
                results.append(np)
        else:
            new_port = deepcopy(src_port)
            if "direction" in new_port:
                new_port["direction"] = _REV_MAP.get(
                    new_port["direction"], new_port["direction"]
                )
            _prefix_port_name(new_port, parent_inst)
            results.append(new_port)
    return results
