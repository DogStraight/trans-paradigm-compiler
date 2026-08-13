"""
AST 调试工具 — 集成到管线的可选调试模块

用法:
    from scripts.ast_debug import dump_ast, dump_tokens, enable_ast_debug

    debug = enable_ast_debug()          # 读取环境变量 DEBUG_AST
    debug = enable_ast_debug(True)       # 强制开启
    dump_ast(ast)                        # 打印 AST 树
    dump_tokens(tokens, 35, 75)          # 打印 token 窗口
"""

import os
import sys

# ---------------------------------------------------------------
# 开关控制
# ---------------------------------------------------------------
_DEBUG_ENABLED = False


def enable_ast_debug(force: bool | None = None) -> bool:
    """启用/查询调试状态。优先级: force > 环境变量 DEBUG_AST > False"""
    global _DEBUG_ENABLED
    if force is not None:
        _DEBUG_ENABLED = bool(force)
    elif not _DEBUG_ENABLED:
        _DEBUG_ENABLED = os.environ.get("DEBUG_AST", "").lower() in ("1", "true", "yes")
    return _DEBUG_ENABLED


# ---------------------------------------------------------------
# AST 结构转储
# ---------------------------------------------------------------
def _get_node_name(node) -> str:
    return getattr(node, "node_name", type(node).__name__)


def _get_attrs(node) -> dict:
    """提取节点上的所有非内置属性"""
    skip = {"node_name", "sub_node"}
    return {k: v for k, v in node.__dict__.items() if k not in skip}


def _fmt_value(v, max_len=40) -> str:
    """格式化属性值"""
    if hasattr(v, "node_name"):
        return f"Node({v.node_name})"
    if hasattr(v, "type"):
        txt = getattr(v, "content", getattr(v, "value", ""))
        if len(txt) > max_len:
            txt = txt[:max_len] + "..."
        return f"Token({v.type} '{txt}')"
    if isinstance(v, list):
        items = []
        for i, item in enumerate(v[:5]):
            items.append(_fmt_value(item))
        if len(v) > 5:
            items.append("...")
        return "[" + ", ".join(items) + f"] (len={len(v)})"
    if v is None:
        return "None"
    s = repr(v)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


def dump_ast(node, indent: int = 0, max_depth: int = 20, file=sys.stdout) -> None:
    """递归打印 AST 树结构"""
    if not enable_ast_debug():
        return
    if indent > max_depth * 2:
        print(" " * indent + "... (max depth)", file=file)
        return

    prefix = " " * indent
    name = _get_node_name(node)
    attrs = _get_attrs(node)
    children = getattr(node, "sub_node", [])

    # 标题行
    if attrs:
        attr_str = ", ".join(f"{k}={_fmt_value(v)}" for k, v in attrs.items())
    else:
        attr_str = ""

    if attr_str:
        print(f"{prefix}◈ {name}  [{attr_str}]", file=file)
    else:
        print(f"{prefix}◈ {name}", file=file)

    # 子节点
    for i, child in enumerate(children):
        print(f"{prefix}  ├─[{i}] ", end="", file=file)
        dump_ast(child, indent + 4, max_depth, file)


def dump_ast_compact(
    node, indent: int = 0, max_depth: int = 15, file=sys.stdout
) -> None:
    """紧凑格式转储 AST（每行一个节点）"""
    if not enable_ast_debug():
        return
    if indent > max_depth * 2:
        return

    prefix = "  " * indent
    name = _get_node_name(node)
    attrs = _get_attrs(node)

    attr_parts = []
    for k, v in attrs.items():
        if hasattr(v, "node_name"):
            attr_parts.append(f"{k}=◈{v.node_name}")
        elif hasattr(v, "type"):
            attr_parts.append(f"{k}=▸{v.type}")
        elif isinstance(v, list):
            attr_parts.append(f"{k}=[{len(v)}]")
        else:
            attr_parts.append(f"{k}={_fmt_value(v)}")

    line = f"{prefix}{name}"
    if attr_parts:
        line += " (" + ", ".join(attr_parts[:3]) + ")"
        if len(attr_parts) > 3:
            line += " ..."

    print(line, file=file)

    for child in getattr(node, "sub_node", []):
        dump_ast_compact(child, indent + 1, max_depth, file)


# ---------------------------------------------------------------
# Token 流查看
# ---------------------------------------------------------------
def dump_tokens(
    tokens,
    start: int = 0,
    end: int | None = None,
    highlight: int | None = None,
    file=sys.stdout,
) -> None:
    """显示 token 窗口，支持高亮指定位置"""
    if not enable_ast_debug():
        return
    if end is None:
        end = len(tokens)

    print(f"── Tokens [{start}..{end}) ──", file=file)
    for i in range(start, min(end, len(tokens))):
        t = tokens[i]
        marker = " >>>" if i == highlight else ""
        txt = repr(getattr(t, "content", getattr(t, "value", "")))
        if len(txt) > 30:
            txt = txt[:27] + "..."
        print(f"  [{i:3d}]{marker} {t.type:30s} {txt}", file=file)


# ---------------------------------------------------------------
# 快速统计
# ---------------------------------------------------------------
def count_ast_nodes(node) -> int:
    """递归统计 AST 节点总数"""
    count = 1
    for child in getattr(node, "sub_node", []):
        count += count_ast_nodes(child)
    return count


def ast_type_distribution(node, dist: dict | None = None) -> dict:
    """统计各节点类型数量"""
    if dist is None:
        dist = {}
    name = _get_node_name(node)
    dist[name] = dist.get(name, 0) + 1
    for child in getattr(node, "sub_node", []):
        ast_type_distribution(child, dist)
    return dist
