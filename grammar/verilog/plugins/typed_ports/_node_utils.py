"""typed_ports 组件内部共用工具 — Node 文本提取 / 类型作用域收集。

`_check.py` / `_expand_ports.py` / `_transform.py` 原先各带一份 `_text`：
前两份逐字相同，第三份是"鸭子类型宽松版"（同类意图、不同边界语义：接受
str、不校验 Node、无 content 时返回 None）。改为共用本模块一份，避免判定
改动时多处漂移；`_collect_type_scopes` 原先在两份文件里各存一份。

Doc: analyzer/semantic_checks.md（检查/展开共用工具）
"""
from core.define import Node


def node_text(node) -> str:
    """Node → 文本（取首个非空 `content`，递归穿透子节点）。

    非 Node：真值 → `str(node)`，假值 → ""。**始终返回 str**——调用方无需
    再做 None 判断（`type_name` / `role_name` 等可选字段缺失时得到空串，
    直接参与拼接/比较都安全）。
    """
    if not isinstance(node, Node):
        return str(node) if node else ""
    content = getattr(node, "content", "") or ""
    if content:
        return content
    for child in node.iter_children():
        t = node_text(child)
        if t:
            return t
    return ""


def collect_type_scopes(root) -> dict:
    """DFS scope 树，收集 kind=type 的作用域 {类型名: Scope}。"""
    out: dict = {}

    def _walk(sc):
        for child in getattr(sc, "children", []) or []:
            if getattr(child, "kind", "") == "type":
                out[child.name] = child
            _walk(child)

    _walk(root)
    return out
