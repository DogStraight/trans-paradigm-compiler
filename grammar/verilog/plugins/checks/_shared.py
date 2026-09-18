"""checks 插件族共用助手 — 赋值目标信号名 / case 臂常量字面量解析。

两个函数原先在 `always_check` / `case_check` / `latch_check` 各存一份同体
实现（本轮外部审计"结构重复"命中），收敛到本模块一份。结构知识
（`Identifier` / `SelectExpr` / `HierExpr` 形态、Verilog 字面量写法）留在
**插件层**，引擎不参与。

Doc: grammar/verilog/plugins/checks/README.md（插件族共用助手）
"""
from core.define import Node


def target_sig(target: Node | None) -> str | None:
    """赋值目标 → 根信号名（Identifier 本体 / SelectExpr 取 base /
    HierExpr 取首段；拼接目标 → None 保守跳过）。
    """
    if not isinstance(target, Node):
        return None
    name = target.node_name
    if name == "Identifier":
        return getattr(target, "content", "") or None
    if name == "SelectExpr":
        return target_sig(getattr(target, "base", None))
    if name == "HierExpr":
        parts = getattr(target, "parts", None) or []
        if parts and isinstance(parts[0], Node):
            return getattr(parts[0], "content", "") or None
        return None
    return None


def const_value(text: str) -> tuple[int, int] | None:
    """case 臂常量文本 → (值, 位宽)；变量/通配符/x/z → None。

    位宽取显式尺寸（`8'hFF` → 8）；无尺寸 → 值的最小位宽（0 → 1 位）。
    单字符 `'0`/`'1`/`'x`/`'z`/`'?` 是**填充/通配符**，不算覆盖 case 臂。
    """
    t = (text or "").strip()
    if "'" not in t:
        if not t.isdigit():
            return None
        v = int(t)
        return (v, v.bit_length() if v else 1)
    body = t.split("'", 1)[1]
    if not body:
        return None
    if body[0] in "sS":
        body = body[1:]
    if not body:
        return None
    if len(body) == 1 and body in "01xXzZ?":
        return None  # 填充/通配符常量不算覆盖
    base_ch = body[0].lower()
    if base_ch not in "bohd":
        return None
    digits = body[1:].replace("_", "")
    if not digits or any(c in "xXzZ?" for c in digits):
        return None
    try:
        v = int(digits, {"b": 2, "o": 8, "h": 16, "d": 10}[base_ch])
    except ValueError:
        return None
    w = int(t.split("'", 1)[0]) if t.split("'", 1)[0].strip().isdigit() \
        else (v.bit_length() if v else 1)
    return (v, w)
