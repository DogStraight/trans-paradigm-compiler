"""_elaborator.py — verilog 精化项与求解器（**语言知识在插件**，ADR-0019）。

引擎侧（`analyzer/elaboration/`）只按项列表驱动「定位 → 求解 → 归位 → 核验」，
不认识任何 Verilog 语义；"世界由哪些事实构成"全部由本文件声明与求解。

## 现役项

**`param_default`**（`unit` 作用域，**无引擎角色位**）
单元参数默认值表 `{参数名: 值表达式文本}`，两处来源合并，**头部优先**：

1. 头部 `#(P = v)` 参数列表（`ModuleDecl.params` → 列表项 `param_name` / `value`）；
2. 体内 `parameter P = v;`（`ParamDeclStmt` → 两层 `items` → `Declarator.name` /
   `init`；含 generate / ifdef 内的声明）。

合并规则与搬迁前 `ModuleExtractor._fill_params` **逐字对齐**（头部同名优先、
体内同名重复声明取先、迭代顺序同用 `core.define.iter_nodes`）——本项是引擎侧同名
实现的原位替代，行为必须一致（回归护栏见 `tools/min_pack_probe.py`）。

**`gen_activity`**（`file` 作用域，`role = gen_activity`）
generate 分支活性 `{id(节点): bool}`；`depends_on = ["param_default"]`（条件求值要
单元常量表，经 `ctx.products` 自取）。语义与搬迁来源见本文件后半段。

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

import re

from core.define import CHILDREN_FIELD, Node, collect_nodes, iter_nodes, unwrap_optional
from core.errors import ConfigError
from core.token_protocol import IDENT_RE

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
_PROVIDES_GEN_ACTIVITY = "gen_activity"
_PROVIDES_PORT_DECLS = "port_decls"
_PROVIDES_CONNECTIONS = "connections"


def build_elaborator() -> dict:
    """能力入口：返回精化能力面（项列表 + 求解函数表）。"""
    return {
        "items": [
            {
                "name": "param_default",
                "scope": "unit",
                # **无**引擎角色位：generate 条件求值已随 gen 族迁入本插件，其求解器经
                # `depends_on` + `ctx.products` 读本项产物 → 引擎不再需要单元常量表
                # （`unit_constants` 角色随 P3-①b 退场）。
                "provides": [_PROVIDES_PARAM_DEFAULT],
                "solver": "solve_param_default",
            },
            {
                "name": "port_decls",
                "scope": "unit",
                # 引擎角色位：层 2/3 的端口形态（P3-② 切换时启用；本项先只新增）
                "role": "unit_ports",
                "provides": [_PROVIDES_PORT_DECLS],
                "solver": "solve_port_decls",
            },
            {
                "name": "connections",
                "scope": "file",
                # 引擎角色位：层 3 与 postpass 消费的连接表（P3-②b 切换时启用）
                "role": "unit_connections",
                "provides": [_PROVIDES_CONNECTIONS],
                "solver": "solve_connections",
            },
            {
                "name": "gen_activity",
                "scope": "file",
                # 引擎角色位：层 3 判"未选中分支的驱动不计"（层 3 迁入协议后删）
                "role": "gen_activity",
                "provides": [_PROVIDES_GEN_ACTIVITY],
                # 条件求值要**单元常量绑定** → 依赖通道（ADR-0019 决策 3）：引擎保证
                # 先跑 param_default；本求解器经 ctx.products 读它，**不经引擎中转**
                "depends_on": ["param_default"],
                "solver": "solve_gen_activity",
            },
        ],
        "solvers": {
            "solve_param_default": solve_param_default,
            "solve_port_decls": solve_port_decls,
            "solve_connections": solve_connections,
            "solve_gen_activity": solve_gen_activity,
        },
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
        for decl, name_node in _decl_name_nodes(node):
            if decl.node_name != _RULE_DECLARATOR:
                continue
            if name_node.content in values:
                continue  # 头部已填（同名重复声明取先）
            init = getattr(decl, _DECL_INIT, None)
            values[name_node.content] = _render(ctx, init)


def _decl_name_nodes(decl_node: Node) -> list[tuple[Node, Node]]:
    """声明节点 → [(声明符节点, 名字节点)]（**两层** `items`，与引擎同形）。

    外层声明节点的 `items` 再套一层声明列表（内层元素挂 `name`）；列表缺失 / 元素非
    节点 / 名字为空 → 不计（与引擎 `ModuleExtractor._decl_name_nodes` 同语义）。
    端口与参数的声明同形，故两处共用本助手。
    """
    outer = getattr(decl_node, _ITEMS, None)
    inner = getattr(outer, _ITEMS, None) if isinstance(outer, Node) else None
    out: list[tuple[Node, Node]] = []
    for d in inner or []:
        if not isinstance(d, Node):
            continue
        dn = getattr(d, _DECL_NAME, None)
        if isinstance(dn, Node) and dn.content:
            out.append((d, dn))
    return out


def _render(ctx: SolveCtx, node: object) -> str:
    """经服务句柄渲染子树 → 文本（非节点 → 空串 = "无值表达式"）。

    服务缺失 = 接线错误 → fail-fast（不静默给空串，否则值静默退化成"无值"）。
    """
    if not isinstance(node, Node):
        return ""
    service = ctx.service
    if service is None:
        raise ConfigError(
            "[elaborator] 本插件的求解器需要渲染服务（ctx.service），调用方未提供"
        )
    return service.render(node)


# ════════════════════════════════════════════════════════════════════════════
# 项 `gen_activity`：generate 条件求值 → 分支活性 `{id(节点): bool}`
# ════════════════════════════════════════════════════════════════════════════
# 语义（对齐 Verilator V3Param::visit(AstGenIf)）：求值 generate 条件、**未选中分支的
# 驱动不计**。tpc 不展开 generate，故按**预计算活性**过滤而非物理删树。
#
# ⚠ 本段是引擎侧 `GenerateEvaluator` + `_GenFace` + 文本常量求值链的**逐字搬迁**：
#   搬迁期必须与之**行为逐项相同**（对拍见
#   `tests/engine/analyzer/test_elaboration_gen_activity.py`）。故此处**不顺手改写成
#   AST-first**——那是独立的改进项（TODO「文本模式求值/判断（应 AST-first）」），
#   要配自己的一套验证。搬迁只搬位置，不改行为。

# ── 本语言包的 generate 形态（原 `[structure]` / `[structure.fields]` 声明） ──
_GEN_BLOCK_RULE = "GenerateBlock"
_GEN_BRANCH_RULES = ("IfBlock", "ElseIfBlock")
_GEN_NOT_OPS = ("!",)
_GEN_CONDITION_FIELD = "condition"
_GEN_THEN_FIELD = "then_stmt"
_GEN_ELSE_FIELD = "else_chain"
_UNIT_DECL_RULE = "ModuleDecl"  # 原 [structure].module_decl_rule
_UNIT_NAME_FIELD = "module_name"  # 原 [structure.fields].module_name


def solve_gen_activity(hits: list[Node], atom: Atom, ctx: SolveCtx) -> dict | None:
    """generate 分支活性：`{id(节点): bool}`（是否落在**选中**的互斥分支内）。

    本项不声明定位（作用域 = `file`）→ `hits = [文件 AST 根]`。
    """
    del atom  # 协议签名参数：产物按原子键（= 文件路径）归位，由驱动器完成
    root = hits[0] if hits else None
    if not isinstance(root, Node):
        return None
    return {_PROVIDES_GEN_ACTIVITY: _precompute_generate_active(root, ctx)}


def _precompute_generate_active(root: Node, ctx: SolveCtx) -> dict[int, bool]:
    """per-file 预计算 `{id(node): bool}`——节点是否在选中的 generate 分支。

    单栈迭代（无递归）：栈元素 = (node, stack, params)。普通节点标记活性后子节点按
    种类入栈（`_gen_push_children`）；generate 块内的条件分支求值后按 then/else 展开
    互斥（`_expand_generate_if`）。节点活性 = 所在分支全部选中。O(树)，查询 O(1)。
    纯迭代实现避免深 AST/嵌套 generate 递归爆栈（picorv32 等大文件，2026-08-29）。

    原引擎实现在"语言包未声明 generate 块规则"时返回空表（不认 generate = 全部节点
    按活跃处理）。本插件形态固定，无此分支——等价于"声明恒定在场"。
    """
    active: dict[int, bool] = {}
    todo: list = [(child, [], {}) for child in root.iter_children()]
    while todo:
        node, stack, params = todo.pop()
        if node is None:
            continue
        active[id(node)] = all(stack)
        _gen_push_children(node, stack, params, todo, ctx)
    return active


def _gen_push_children(
    node, stack: list, params: dict, todo: list, ctx: SolveCtx
) -> None:
    """按节点种类把子节点入栈（generate 遍历的分派点）。

    - generate 块：条件分支子块交 `_expand_generate_if` 展开互斥；其余沿用当前活性
    - 模块声明：子节点以本模块**参数表**入栈（条件求值用）
    - 其他（含 always 内普通 if）：普通遍历，活性继承当前栈——非 generate 条件不互斥
    """
    if node.node_name == _GEN_BLOCK_RULE:
        _push_generate_children(node, stack, params, todo, ctx)
        return
    if node.node_name == _UNIT_DECL_RULE:
        _push_module_children(node, todo, ctx)
        return
    for child in node.iter_children():
        todo.append((child, stack, params))


def _push_generate_children(
    node, stack: list, params: dict, todo: list, ctx: SolveCtx
) -> None:
    """generate 块子块入栈：条件分支求值展开互斥，其余沿用当前活性。"""
    for sub in getattr(node, CHILDREN_FIELD, None) or []:
        if not isinstance(sub, Node):
            continue
        if sub.node_name in _GEN_BRANCH_RULES:
            _expand_generate_if(sub, stack, params, todo, ctx)
        else:
            todo.append((sub, stack, params))


def _push_module_children(node, todo: list, ctx: SolveCtx) -> None:
    """模块声明子节点入栈：以本模块**参数表**入栈（条件求值用）。

    参数表 = 本语言包**自己**的前一项产物（`depends_on = ["param_default"]`），经
    `ctx.products` 直接读——**不经引擎中转**（这正是依赖通道的用途）。
    """
    name_node = getattr(node, _UNIT_NAME_FIELD, None)
    unit_name = getattr(name_node, "content", "") or ""
    defaults = (ctx.products.get(_PROVIDES_PARAM_DEFAULT) or {}).get(unit_name, {})
    params: dict[str, str] = dict(defaults or {})
    for child in node.iter_children():
        todo.append((child, [], params))


def _expand_generate_if(
    ifb, stack: list, params: dict, todo: list, ctx: SolveCtx
) -> None:
    """条件分支：条件求值，then/else 分支展开入栈（else-if 链活性叠加）。

    else-if 链：外层条件为假时进入链，链内条件独立求值但活性叠加外层"假"
    （FAST=0 且 MUL=1 → MUL 分支选中）。条件不可判 → 整块按当前活性展开（保守）。
    纯迭代无递归。
    """
    # 链入口：当前栈 + 之前所有 else-if 的条件取假（首块无前置）
    base = list(stack)
    cur = ifb
    while isinstance(cur, Node) and cur.node_name in _GEN_BRANCH_RULES:
        cond_val = _eval_gen_cond(cur, params, ctx)
        then_node = getattr(cur, _GEN_THEN_FIELD, None)
        chain = getattr(cur, _GEN_ELSE_FIELD, None)
        if cond_val is None:
            todo.append((cur, base, params))
            return
        # then 分支：base（外层全假）+ 本条件真
        todo.append((then_node, base + [cond_val], params))
        if isinstance(chain, Node) and chain.node_name in _GEN_BRANCH_RULES:
            # 进入链：外层再加"本条件假"
            base = base + [not cond_val]
            cur = chain
            continue
        # 最终 else：base（外层全假）+ 本条件假
        todo.append((chain, base + [not cond_val], params))
        return


def _eval_gen_cond(ifb: Node, params: dict, ctx: SolveCtx) -> bool | None:
    """条件分支的条件字段 → 布尔｜None（不可判）。

    条件文本（HierExpr/Identifier/常量表达式）→ 查参数表 → 数值求值转布尔。
    不可判（无参数值/非纯常量/引用未定义）→ None 保守。

    ⚠ 这是**文本模式**求值（原引擎实现如此，搬迁期不改行为）：先经服务句柄把条件
    子树渲染成文本再解析。AST-first 改写是独立改进项。
    """
    cond = getattr(ifb, _GEN_CONDITION_FIELD, None)
    text = (_render(ctx, cond) if isinstance(cond, Node) else "") or ""
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text) != 0
    if text in params:
        return _param_truth(params[text])
    # 逻辑非前缀 + 参数名（前缀表 = 本插件声明；引擎不认识 `!` 这个拼写）
    for op in _GEN_NOT_OPS:
        if not text.startswith(op):
            continue
        name = text[len(op) :].strip()
        if IDENT_RE.fullmatch(name) and name in params:
            val = _param_truth(params[name])
            return None if val is None else not val
    # 含运算的纯常量表达式（`1+0` / `2*3<7` 等）→ 显式求值（不用 eval）；
    # 标识符/位运算/逻辑运算等一律不可判 → None
    return _eval_const_expr(text)


def _param_truth(raw: str) -> bool | None:
    """参数值文本 → 真值（纯数字非零为真）；非纯数字 → None（不可判）。"""
    v = (raw or "").strip()
    return int(v) != 0 if v.isdigit() else None


# ── 常量表达式求值（原 `analyzer/structure.py` 顶部三块，逐字搬迁） ──
# 只认中性形态（数字/括号/四则/比较——多数语言同形）；位运算、逻辑运算、标识符、
# 三目一律不可判：那是语言层的事（本语言包侧另有求值器，如 latch_check）。
_CONST_TOK_RE = re.compile(r"[ ]*(?:(\d+)|(<=|>=|==|!=|\+|-|\*|/|%|\(|\)|<|>))")
_CMP_OPS = ("<", "<=", ">", ">=", "==", "!=")


def _tokenize_const(text: str) -> list[tuple[str, str]] | None:
    """常量表达式 → token 列表；出现未声明的字符 → None（不可判）。"""
    toks: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _CONST_TOK_RE.match(text, pos)
        if m is None:
            return None
        pos = m.end()
        toks.append(
            ("num", m.group(1)) if m.group(1) is not None else ("op", m.group(2))
        )
    return toks


class _ConstExprParser:
    """常量表达式递归下降求值器（游标即状态，故用类而非闭包）。

    语法见 `_eval_const_expr`；任一步不可判 → None 向上冒泡（保守）。
    """

    def __init__(self, toks: list[tuple[str, str]]) -> None:
        self.toks = toks
        self.pos = 0

    def parse(self) -> bool | None:
        """整串求值：必须消费完所有 token，否则不可判。"""
        val = self._cmp()
        if val is None or self.pos != len(self.toks):
            return None
        return bool(val)

    def _peek(self) -> tuple[str, str] | None:
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def _eat(self) -> tuple[str, str]:
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    def _primary(self) -> float | None:
        """基本项：数字 | '(' 表达式 ')'。"""
        cur = self._peek()
        if cur is None:
            return None
        kind, tok = cur
        if tok == "(":
            self._eat()
            val = self._cmp()
            nxt = self._peek()
            if val is None or nxt is None or nxt[1] != ")":
                return None
            self._eat()
            return val
        if kind == "num":
            self._eat()
            return float(tok)
        return None

    def _unary(self) -> float | None:
        """一元：('+'|'-')* 基本项（符号链逐层取负）。"""
        cur = self._peek()
        if cur is not None and cur[1] in ("+", "-"):
            sign = self._eat()[1]
            val = self._unary()
            if val is None:
                return None
            return -val if sign == "-" else val
        return self._primary()

    def _term(self) -> float | None:
        """乘除模：左结合；除/模零 → 不可判。"""
        left = self._unary()
        if left is None:
            return None
        while True:
            cur = self._peek()
            if cur is None or cur[1] not in ("*", "/", "%"):
                return left
            op = self._eat()[1]
            right = self._unary()
            if right is None or (op in ("/", "%") and right == 0):
                return None
            if op == "*":
                left *= right
            elif op == "/":
                left /= right
            else:
                left %= right

    def _sum(self) -> float | None:
        """加减：左结合。"""
        left = self._term()
        if left is None:
            return None
        while True:
            cur = self._peek()
            if cur is None or cur[1] not in ("+", "-"):
                return left
            op = self._eat()[1]
            right = self._term()
            if right is None:
                return None
            left = left + right if op == "+" else left - right

    def _cmp(self) -> float | None:
        """比较：结果折算 1.0/0.0（布尔参与后续比较：真=1 / 假=0）。"""
        left = self._sum()
        if left is None:
            return None
        while True:
            cur = self._peek()
            if cur is None or cur[1] not in _CMP_OPS:
                return left
            op = self._eat()[1]
            right = self._sum()
            if right is None:
                return None
            ok = {
                "<": left < right,
                "<=": left <= right,
                ">": left > right,
                ">=": left >= right,
                "==": left == right,
                "!=": left != right,
            }[op]
            left = 1.0 if ok else 0.0


def _eval_const_expr(text: str) -> bool | None:
    """纯常量表达式求值 → 布尔｜None（不可判，保守）。

    显式递归下降（`_ConstExprParser`），**不用 `eval`**：源码文本进 `eval` 是 RCE 面；
    且 Python 词法与目标语言不一致——`!`/`&&`/`||` 在 Python 里是语法错，只会静默落回
    不可判，写进白名单反而看不出真实可达面。

    语法：表达式 := 比较；比较 := 加减 (比较符 加减)*；加减 := 乘除 (('+'|'-') 乘除)*；
    乘除 := 一元 (('*'|'/'|'%') 一元)*；一元 := ('+'|'-')* 基本项；
    基本项 := 数字 | '(' 表达式 ')'。
    """
    toks = _tokenize_const(text.strip())
    if toks is None:
        return None
    return _ConstExprParser(toks).parse()


# ════════════════════════════════════════════════════════════════════════════
# 项 `port_decls`：单元端口声明表
# ════════════════════════════════════════════════════════════════════════════
# 三种声明形态合并（与引擎 `ModuleExtractor._fill_ports` **逐字对齐**）：
#   ① ANSI 头部逐项（方向 / 宽度 / 网络类型）；
#   ② 头部裸名项（`(a, b, y)` 形态，仅登记名字）；
#   ③ 体内旧式声明（`input [7:0] a;`）→ 按名**回填**方向/宽度，未登记则补登记。
# 同名时**头部优先**（回填只补空字段）；body 声明不带网络类型。
#
# ⚠ P3-②a 阶段本项是**只新增**（引擎侧 `ModuleInfo.ports` 仍在原位、仍是层 2/3 的
#   输入），故此刻**无人消费它**——存在意义是与引擎产物做**等价性对拍**（见
#   `tests/engine/analyzer/test_elaboration_port_decls.py`）。切换 + 删引擎侧在 P3-②b。

# ── 本语言包的端口形态（原 `[structure]` / `[structure.fields]` 声明） ──
_UNIT_PORTS = "ports"
_BARE_PORT_RULE = "Identifier"
_PORT_DECL = "decl"  # 包装字段（inline 规则防御穿透）
_PORT_DIRECTION = "direction"
_PORT_WIDTH = "packed_range"
_PORT_TYPE = "port_type"
_BODY_PORT_RULES = ("BodyInputDecl", "BodyOutputDecl", "BodyInoutDecl")
# 函数/任务子树整体跳过（其参数与模块体端口同节点名；见 `_collect_body_ports`）
_FUNC_OR_TASK = ("FuncDecl", "FuncDeclOld", "TaskDecl", "FunctionDecl", "TaskDeclStmt")


def solve_port_decls(hits: list[Node], atom: Atom, ctx: SolveCtx) -> dict | None:
    """单元端口声明表 `{端口名: {name, direction, width_expr, net_type, decl_node}}`。

    本项不声明定位（作用域 = `unit`）→ `hits = [单元节点]`。
    `decl_node._file` 会写成本原子所属文件——related 链跨文件定位要用（引擎侧
    `_register_port` 同款副作用），故此处不能丢。
    """
    unit = hits[0] if hits else None
    if not isinstance(unit, Node):
        return None
    ports: dict[str, dict] = {}
    _collect_ansi_ports(unit, ports, ctx, atom.path)
    _collect_body_ports(unit, ports, ctx, atom.path)
    return {_PROVIDES_PORT_DECLS: ports}


def _new_port(
    name: str,
    path: str,
    direction: str = "",
    width_expr: str = "",
    net_type: str = "",
    decl_node: Node | None = None,
) -> dict:
    if decl_node is not None:
        decl_node._file = path  # related 链跨文件定位
    return {
        "name": name,
        "direction": direction,
        "width_expr": width_expr,
        "net_type": net_type,
        "decl_node": decl_node,
    }


def _collect_ansi_ports(
    unit: Node, ports: dict[str, dict], ctx: SolveCtx, path: str
) -> None:
    """头部端口列表：裸名项只登记名字，其余按 ANSI 项逐名登记。"""
    holder = unwrap_optional(getattr(unit, _UNIT_PORTS, None))
    items = getattr(holder, _ITEMS, None) if isinstance(holder, Node) else None
    for item in items or []:
        if not isinstance(item, Node):
            continue
        if item.node_name == _BARE_PORT_RULE:
            if item.content:
                ports[item.content] = _new_port(item.content, path)
            continue
        _register_ansi_item(item, ports, ctx, path)


def _register_ansi_item(
    item: Node, ports: dict[str, dict], ctx: SolveCtx, path: str
) -> None:
    """ANSI 端口项 → 逐名登记（方向 / 宽度 / 网络类型）。

    ANSI 风格：端口声明规则 inline 展平，item 即具体声明；防御：也可能是**未展平**的
    包装节点（取其 `decl` 字段）。
    """
    decl = getattr(item, _PORT_DECL, None)
    if isinstance(decl, Node):
        item = decl
    direction = getattr(item, _PORT_DIRECTION, "") or ""
    pr = getattr(item, _PORT_WIDTH, None)
    width = _render(ctx, pr) if isinstance(pr, Node) else ""
    pt = getattr(item, _PORT_TYPE, None)
    net_type = _render(ctx, pt) if isinstance(pt, Node) else ""
    for d, dn in _decl_name_nodes(item):
        ports[dn.content] = _new_port(dn.content, path, direction, width, net_type, d)


def _collect_body_ports(
    unit: Node, ports: dict[str, dict], ctx: SolveCtx, path: str
) -> None:
    """体内旧式端口声明 → 按名回填方向/宽度（未登记则补登记）。

    只扫模块体，**跳过函数/任务子树**——函数参数（`input [3:0] A`）与模块体端口同
    节点名（`BodyInputDecl`），全子树遍历会把函数局部 input 误当模块端口
    （2026-08-29 对标测试暴露：tv80_alu 的 AddSub4 函数参数 A/B/Sub/Carry_In 被误
    登记为模块端口 → 8 条 W104 假阳性；Verilator 0 报 PINMISSING）。纯迭代无递归。
    """
    stack = list(unit.iter_children())
    while stack:
        node = stack.pop()
        if not isinstance(node, Node):
            continue
        if node.node_name in _FUNC_OR_TASK:
            continue  # 函数/任务子树整体跳过（参数非模块端口）
        if node.node_name in _BODY_PORT_RULES:
            _backfill_body_port_node(node, ports, ctx, path)
        # 继续下钻（Body*Decl 自身无端口子节点，正常下钻函数兄弟）
        for child in node.iter_children():
            stack.append(child)


def _backfill_body_port_node(
    node: Node, ports: dict[str, dict], ctx: SolveCtx, path: str
) -> None:
    """单个 body 端口声明节点 → 按名回填（body 声明**不带网络类型**）。"""
    direction = getattr(node, _PORT_DIRECTION, "") or ""
    pr = getattr(node, _PORT_WIDTH, None)
    width = _render(ctx, pr) if isinstance(pr, Node) else ""
    for d, dn in _decl_name_nodes(node):
        existing = ports.get(dn.content)
        if existing is None:
            ports[dn.content] = _new_port(dn.content, path, direction, width, "", d)
            continue
        existing["direction"] = existing["direction"] or direction
        existing["width_expr"] = existing["width_expr"] or width
        if existing["decl_node"] is None:
            d._file = path
            existing["decl_node"] = d


# ════════════════════════════════════════════════════════════════════════════
# 项 `connections`：实例化点端口连接展开（层 2，per-file）
# ════════════════════════════════════════════════════════════════════════════
# 与引擎 `ConnectionElaborator.elaborate_connections` **逐字对齐**：
#   - **命名连接** `.p(sig)`（项上有非空 `port_name`）→ `connects[端口名] = 值文本`；
#   - 其余项 = **位置连接**，按出现序进 `ordered`（值 = 连接表达式文本）。
#
# ✅ 一个曾经担心的风险，实测**不存在**：层 2 **完全不读端口表**（不用 `module_index` /
#   ports）——它只读**声明字段**（实例名 / 连接字段 / 端口名 / 值）并把表达式渲染成文本。
#   故"发现过程中逐文件算"与"发现之后统一算"**结果相同**，搬迁无时序风险。
#
# ⚠ 本阶段本项**只新增**（引擎 `FileResult.connections` 仍在原位、仍是层 3 与 postpass
#   的输入），存在意义是与引擎产物做**逐项对拍**。

# ── 本语言包的实例化形态（原 `[structure]` / `[structure.fields]` 声明） ──
_INST_RULE = "ModuleInst"
_INST_NAME = "inst_name"
_INST_CONNECTS = "ports"  # 连接列表字段（[structure.fields].connects 的值）
_PORT_NAME = "port_name"
_CONN_VALUE = "value"


def solve_connections(hits: list[Node], atom: Atom, ctx: SolveCtx) -> dict | None:
    """文件内实例化点的连接展开表（层 2）。

    本项不声明定位（作用域 = `file`）→ `hits = [文件 AST 根]`；实例化点按**声明的实例
    规则名**自行收集（`collect_nodes`，与引擎 `FileResult.inst_sites` 同源）。
    """
    root = hits[0] if hits else None
    if not isinstance(root, Node):
        return None
    conns = [
        _elaborate_connection(site, atom.path, ctx)
        for site in collect_nodes(root, _INST_RULE)
    ]
    return {_PROVIDES_CONNECTIONS: conns}


def _elaborate_connection(site: Node, path: str, ctx: SolveCtx) -> dict:
    """单个实例化点 → 连接展开（命名连接进 connects，其余按位置序进 ordered）。"""
    connects: dict[str, str] = {}
    ordered: list[str] = []
    for item in _connection_items(site):
        if not isinstance(item, Node):
            continue
        pn = getattr(item, _PORT_NAME, None)
        pn_text = pn.content if isinstance(pn, Node) and pn.content else ""
        if pn_text:
            val = getattr(item, _CONN_VALUE, None)
            connects[pn_text] = _render(ctx, val) if isinstance(val, Node) else ""
            continue
        # 其余项 = 位置连接（Expression/HierExpr 等，渲染回文本）
        ordered.append(_render(ctx, item))
    return {
        "inst_name": _inst_name_of(site),
        "module_name": _inst_module_name(site),
        "inst_node": site,
        "file": path,
        "connects": connects,
        "ordered": ordered,
    }


def _connection_items(site: Node) -> list:
    """实例化点的连接项列表（连接字段 → 容器节点 → `items` 字段）。"""
    holder = unwrap_optional(getattr(site, _INST_CONNECTS, None))
    items = getattr(holder, _ITEMS, None) if isinstance(holder, Node) else None
    return list(items or [])


def _inst_name_of(site: Node) -> str:
    """实例名（实例化点 `inst_name` 字段文本；缺省 ""）。"""
    node = getattr(site, _INST_NAME, None)
    return node.content if isinstance(node, Node) and node.content else ""


def _inst_module_name(site: Node) -> str:
    """被实例化模块名（实例化点 `module_name` 字段文本；缺省 ""）。"""
    node = getattr(site, _UNIT_NAME_FIELD, None)
    return node.content if isinstance(node, Node) and node.content else ""
