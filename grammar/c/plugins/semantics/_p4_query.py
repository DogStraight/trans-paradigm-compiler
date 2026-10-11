"""_p4_query.py — P4 专用符号查询：`(name)` 处**该名是不是类型名**。

为什么不用 shipped `_api.is_typedef`（实测，二者不可兼得）：
  · 目标输入（全局 typedef + 块内使用）用**真实作用域路径**去查 ⇒ 精确 scope 不匹配
    任何记录 ⇒ **误拒**（False）；
  · 遮蔽例（块内/参数同名）用 `scope=None` 去查 ⇒ 只看"存在同名 typedef 记录"
    ⇒ **误接受**（True，而 C/gcc 判非法）。
故 P4 自研本查询，判定四件事（缺一即错）：

  1. **祖先作用域**：声明所在作用域必须是使用点作用域的祖先（或同一）——路径按段比较，
     `<global>` 是 `<global>/FuncDef/CompoundStmt` 的祖先；
  2. **最近声明遮蔽**：可见记录里取"最深作用域 → 最新声明序"的那一条为**唯一定序**；
     **最近声明不是类型名（如变量/参数）即拒绝**，不回退到更外层的同名 typedef（回退
     会让遮蔽例误接受）；
  3. **`(decl_order, line, column)` 顺序**："最近声明"必须**先于**使用点。同行先后不能
     只靠行号：优先用使用点的**声明序**（契约 `raw_order`）；只有行号且同行 ⇒ **不可判
     ⇒ 拒绝**（沿用未声明标识符的默认偏置 `not typedef`，宁可拒绝不误接受）；
  4. **tag 排除**：标签（`struct/union/enum` 的 tag）属**另一个命名空间**，不参与
     "是不是类型名"的判定（`struct t{}; (t)y;` 必须拒绝），故在筛选可见记录时排除。

判定只用 `phase == "analyze"` 的记录（`pre_scan` 期是粗收集，不作判定依据）；无任何
可见记录 ⇒ False（默认偏置，见 `_api.DEFAULT_TYPEDEF_BIAS`）。

kind 语义由 **C 包声明**（本模块顶部的两组常量；第二步的通用原语会从包配置传入，
本模块保持可覆盖参数）。核心是"语言知识在包侧、算法在通用面"。
Doc: grammar/c/README.md（符号收集产物）/ docs/gaps/gap-c-semantic-base.md（P4）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

# ── C 包声明：哪些 kind 构成"类型名"、哪些 kind 属**别的命名空间**（不参与判定） ──
#: 构成类型名的 kind（C：typedef 名；C23 后仍只有 typedef 进入普通标识符的"类型"角色）
TYPE_NAME_KINDS: tuple[str, ...] = ("typedef",)
#: 另一个命名空间的 kind（标签）：参与判定会把 `struct t{}; (t)y;` 误判为转换
OTHER_NAMESPACE_KINDS: tuple[str, ...] = ("tag",)
#: 可作判定依据的期别（`pre_scan` 是粗收集，只作提示）
DECIDABLE_PHASES: tuple[str, ...] = ("analyze",)


@dataclass(frozen=True)
class UseSite:
    """使用点：`raw` 节点提供的 `(line, column, order)` + analyzer 侧给出的作用域路径。

    - `scope`：使用点所处作用域路径（analyzer 遍历走到该节点时的 scope，如
      `<global>/FuncDef/CompoundStmt`）；
    - `order`：使用点的**声明序序号**（契约 `raw_order`）——同行先用后声明只能靠它判；
    - `line`/`column`：使用点源位置（缺 order 时的退路；同行不可判 ⇒ 拒绝）。
    """

    name: str
    scope: str
    order: int | None = None
    line: int | None = None
    column: int | None = None


def _segments(path: Any) -> list[str]:
    return [s for s in str(path or "").split("/") if s]


def _is_visible(decl_scope: Any, use_scope: str) -> bool:
    """声明作用域是否为使用点作用域的祖先（或同一作用域）——按路径段比较。"""
    decl = _segments(decl_scope)
    use = _segments(use_scope)
    return len(decl) <= len(use) and use[: len(decl)] == decl


def _order_key(rec: dict) -> tuple[int, int, int]:
    """记录的声明序键 `(decl_order, decl_line, decl_column)`；缺项取哨兵（排前）。"""
    order, line, column = rec.get("decl_order"), rec.get("decl_line"), rec.get("decl_column")
    return (
        order if isinstance(order, int) else -1,
        line if isinstance(line, int) else 0,
        column if isinstance(column, int) else 0,
    )


def _precedes(rec: dict, use: UseSite) -> bool:
    """"最近声明"是否**先于**使用点。无位置信息时按作用域/最近声明判（文档写明）。"""
    decl_order = rec.get("decl_order")
    if use.order is not None and isinstance(decl_order, int):
        return decl_order < use.order
    decl_line = rec.get("decl_line")
    if use.line is not None and isinstance(decl_line, int):
        # 严格小于：同行 ⇒ 无法证明"声明在前"（列信息在 records 侧不保证）
        # ⇒ 拒绝（默认偏置 not typedef，宁可拒绝不误接受）
        return decl_line < use.line
    return True


def nearest_declaration(
    use: UseSite,
    records: Sequence[dict],
    *,
    excluded_kinds: Sequence[str] = OTHER_NAMESPACE_KINDS,
) -> dict | None:
    """按"祖先作用域 + 最近声明"选出**唯一定序**的可见声明（无则 None）。

    选择键 = `(作用域深度, (decl_order, decl_line, decl_column))` 取最大：
    先看作用域深度（内层遮蔽外层），同深度取最新声明（同作用域重声明时"最后一条"生效）。
    标签等**别的命名空间**的 kind 直接排除，不参与竞争。
    """
    candidates = [
        rec
        for rec in records
        if rec.get("name") == use.name
        and rec.get("phase") in DECIDABLE_PHASES
        and rec.get("kind") not in excluded_kinds
        and _is_visible(rec.get("scope"), use.scope)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (len(_segments(r.get("scope"))), _order_key(r)))


def is_type_name(
    use: UseSite,
    records: Sequence[dict],
    *,
    type_kinds: Sequence[str] = TYPE_NAME_KINDS,
    excluded_kinds: Sequence[str] = OTHER_NAMESPACE_KINDS,
) -> bool:
    """`use` 处的名字是否为类型名（P4 判定；`type_kinds` 由包声明）。

    判定链：可见性筛（祖先作用域 + 排除别的命名空间）→ 最近声明 → 最近声明属类型名
    → 最近声明先于使用点。任一不满足 ⇒ False（**无回退、不静默**：最近声明不是类型名
    即拒绝；不可判即拒绝）。
    """
    nearest = nearest_declaration(use, records, excluded_kinds=excluded_kinds)
    if nearest is None:
        return False  # 未声明 ⇒ 默认偏置 not typedef
    if nearest.get("kind") not in type_kinds:
        return False  # 最近声明是变量/参数/枚举常量/… ⇒ 拒绝（不回退外层同名 typedef）
    return _precedes(nearest, use)
