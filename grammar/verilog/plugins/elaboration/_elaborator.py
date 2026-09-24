"""_elaborator.py — verilog 精化项与求解器（**语言知识在插件**，ADR-0019）。

引擎侧（`analyzer/elaboration/`）只按项列表驱动「定位 → 求解 → 归位 → 核验」，
不认识任何 Verilog 语义；"世界由哪些事实构成"全部由本文件声明与求解。

## 现役项

**`param_default`**（`unit` 作用域，`role = unit_constants`）
单元参数默认值表 `{参数名: 值表达式文本}`，两处来源合并，**头部优先**：

1. 头部 `#(P = v)` 参数列表（`ModuleDecl.params` → 列表项 `param_name` / `value`）；
2. 体内 `parameter P = v;`（`ParamDeclStmt` → 两层 `items` → `Declarator.name` /
   `init`；含 generate / ifdef 内的声明）。

合并规则与搬迁前 `ModuleExtractor._fill_params` **逐字对齐**（头部同名优先、
体内同名重复声明取先、迭代顺序同用 `core.define.iter_nodes`）——本项是引擎侧同名
实现的原位替代，行为必须一致（回归护栏见 `tools/min_pack_probe.py`）。

## 为什么本项不声明定位

值分散在"头部字段"与"体内 `ParamDeclStmt`"两种形态，**单条规则名表达不了**；
"怎么找"本身就是语言知识 → 归本插件自行走子树（协议允许 `locator` / `locator_fn`
都省略，此时求解器收到 `hits = [原子根]`）。

## 字段名为什么写在这里

`params` / `param_name` / `value` / `items` / `name` / `init` 是**本语言包自己的语法
绑定**（见 `base/_structure.toml` 的 `[structure.fields]`）——按 ADR-0019 决策 1，
语言知识归插件，故写在本文件；后者是引擎侧的**过渡**声明面，随各族搬迁退场。
"""
from __future__ import annotations

from core.define import Node, iter_nodes, unwrap_optional
from core.errors import ConfigError

from analyzer.elaboration.driver import Atom, SolveCtx

# ── 本语言包的语法绑定（同 base/_structure.toml [structure.fields]） ──
_UNIT_PARAMS = "params"  # ModuleDecl.params（外层容器）
_PARAM_NAME = "param_name"  # 头部参数项上的参数名
_PARAM_VALUE = "value"  # 头部参数项上的值表达式
_ITEMS = "items"  # 列表容器字段（ParamDeclStmt.items.items）
_DECL_NAME = "name"  # Declarator.name
_DECL_INIT = "init"  # Declarator.init（体内参数默认值）

_RULE_BODY_PARAM = "ParamDeclStmt"
_RULE_DECLARATOR = "Declarator"

_PROVIDES_PARAM_DEFAULT = "param_default"


def build_elaborator() -> dict:
    """能力入口：返回精化能力面（项列表 + 求解函数表）。"""
    return {
        "items": [
            {
                "name": "param_default",
                "scope": "unit",
                # 引擎角色位：过渡期生成条件求值需要"单元常量绑定"（gen 族搬迁后删）
                "role": "unit_constants",
                "provides": [_PROVIDES_PARAM_DEFAULT],
                "solver": "solve_param_default",
            },
        ],
        "solvers": {"solve_param_default": solve_param_default},
    }


# ── 求解 ──

def solve_param_default(
    hits: list[Node], atom: Atom, ctx: SolveCtx
) -> dict | None:
    """单元参数默认值表（头部 + 体内，头部优先）。"""
    del atom  # 协议签名参数：本项不声明定位，输入即 `hits`
    unit = hits[0] if hits else None
    if not isinstance(unit, Node):
        return None
    values: dict[str, str] = {}
    _collect_header_params(unit, values, ctx)
    _collect_body_params(unit, values, ctx)
    return {_PROVIDES_PARAM_DEFAULT: values}


def _collect_header_params(unit: Node, values: dict[str, str], ctx: SolveCtx) -> None:
    """头部 `#(P = v)` 列表 → 参数表（两层 `params` 容器，与引擎同形）。"""
    holder = unwrap_optional(getattr(unit, _UNIT_PARAMS, None))
    params = getattr(holder, _UNIT_PARAMS, None) if isinstance(holder, Node) else None
    for p in params or []:
        _register_header_param(p, values, ctx)


def _register_header_param(p: object, values: dict[str, str], ctx: SolveCtx) -> None:
    """单个头部参数项 → 参数表（非节点 / 无名字 → 跳过）。"""
    if not isinstance(p, Node):
        return
    p = unwrap_optional(p)  # 参数项可能被 optional 包装
    if not isinstance(p, Node):
        return
    name_node = getattr(p, _PARAM_NAME, None)
    if not isinstance(name_node, Node) or not name_node.content:
        return
    value_node = getattr(p, _PARAM_VALUE, None)
    values[name_node.content] = _render(ctx, value_node)


def _collect_body_params(unit: Node, values: dict[str, str], ctx: SolveCtx) -> None:
    """体内 `parameter P = v;` → 参数表（头部已填的同名跳过 = 取先）。"""
    for node in iter_nodes(unit):
        if node.node_name != _RULE_BODY_PARAM:
            continue
        for decl in _declarators_of(node):
            if decl.node_name != _RULE_DECLARATOR:
                continue
            name_node = getattr(decl, _DECL_NAME, None)
            if not isinstance(name_node, Node) or not name_node.content:
                continue
            if name_node.content in values:
                continue  # 头部已填（同名重复声明取先）
            init = getattr(decl, _DECL_INIT, None)
            values[name_node.content] = _render(ctx, init)


def _declarators_of(decl_node: Node) -> list[Node]:
    """声明语句 → 声明符列表（**两层** `items`，与引擎 `_decl_name_nodes` 同形）。"""
    outer = getattr(decl_node, _ITEMS, None)
    inner = getattr(outer, _ITEMS, None) if isinstance(outer, Node) else None
    return [d for d in (inner or []) if isinstance(d, Node)]


def _render(ctx: SolveCtx, node: object) -> str:
    """经服务句柄渲染子树 → 值文本（非节点 → 空串 = "无值表达式"）。

    服务缺失 = 接线错误 → fail-fast（不静默给空串，否则参数值静默退化成"无值"）。
    """
    if not isinstance(node, Node):
        return ""
    service = ctx.service
    if service is None:
        raise ConfigError(
            "[elaborator] 项 'param_default' 需要渲染服务（ctx.service），"
            "调用方未提供"
        )
    return service.render(node)
