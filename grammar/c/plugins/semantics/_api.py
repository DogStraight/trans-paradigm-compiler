"""_api.py — C 包符号收集产物的**纯逻辑**（无注册副作用；装配面见 `_symbols.py`）。

定位（`docs/gaps/gap-c-semantic-base.md`）：符号基座的**后置**一半——复用引擎既有
`analyzer/scope.py::Scope/Symbol` 骨架与声明式原语（`[Rule.analyzer]`），产出只读、
可查询的符号记录表；本片**不改 parser**、不做 `(myint)x` 判定、只增不改既有行为。

产物形状（每条记录，JSON 可序列化）：

    {"name": str,            # 符号名
     "kind": str,            # typedef / tag / variable / function / enumerator
     "scope": str,           # 作用域路径（"<global>/f/CompoundStmt"）
     "scope_kind": str|None, # global / function / block
     "decl_order": int|None, # analyze 期 = 收集序（≈ 源序，供"先声明后使用"判定）
     "decl_line": int|None,  # 声明所在源行（parser 挂的 _pos_line）
     "phase": str}           # "analyze"（本插件）/ "pre_scan"（lexer 预扫描）

**分期（作者硬要求）**：`phase` 标注"名称来自哪个时期"——
`pre_scan`（`lexer/pre_scan.py`：文本级/平坦/首见归属，只作提示）与
`analyze`（本插件：精确作用域 + 声明序）。同一位点两期都有记录时**两条都保留**
（`merge_phases`/`phases_for` 供对比），形态判定一律以 `analyze` 为准。

**默认偏置（显式化）**：未声明标识符按 `DEFAULT_TYPEDEF_BIAS = "not typedef"` 处理——
`is_typedef()` 的缺省即此值；调用点不得再各自硬编码。
Doc: grammar/c/README.md（符号收集产物：形状 / 分期语义 / 默认偏置）
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from core.define import Node
from analyzer.scope import Scope

# ── 期别 / 偏置 / 产物键（调用方只读这些常量，勿在别处硬编码） ──
PHASE_PRE_SCAN = "pre_scan"
PHASE_ANALYZE = "analyze"
#: 预扫描期作用域未知（平坦收集）——固定标记而非 None，便于按 scope 过滤时区分"未知"与"缺值"
SCOPE_FILE_UNKNOWN = "<file>"
#: 未声明标识符的默认偏置（显式口径：不是 typedef 名）
DEFAULT_TYPEDEF_BIAS = "not typedef"
#: 产物在 `AnalysisContext.extra` 中的键（与 `[[analyzer.postpasses]] produces` 同名）
PRODUCT_KEY = "c_symbols"

KIND_TYPEDEF = "typedef"
KIND_TAG = "tag"
KIND_VARIABLE = "variable"
KIND_FUNCTION = "function"
KIND_ENUMERATOR = "enumerator"


def scope_path(scope: Scope | None) -> str:
    """作用域 → 路径字符串（自根到当前，走 `Scope` 骨架自带的 parent 链）。"""
    if scope is None:
        return SCOPE_FILE_UNKNOWN
    names: list[str] = []
    cur: Scope | None = scope
    while cur is not None:
        names.append(cur.name)
        cur = cur.parent
    return "/".join(reversed(names))


def _walk(node: Node, path: str) -> list[Any]:
    """沿点分路径取叶子值；`list` 节点自动展开（无位置语法的简化版路径）。

    例：`declarators.items.declarator.direct.head.content` 取到每个声明符的
    `Identifier.content`（声明名）。路径不存在 → 空表（不报错：匿名/省略形态合法）。
    """
    parts = [p for p in path.split(".") if p]
    current: list[Any] = [node]
    for part in parts:
        nxt: list[Any] = []
        for item in current:
            if isinstance(item, list):
                nxt.extend(x for x in item if x is not None)
            elif isinstance(item, Node):
                val = getattr(item, part, None)
                if isinstance(val, list):
                    nxt.extend(val)
                elif val is not None:
                    nxt.append(val)
        current = nxt
        if not current:
            return []
    return current


def _as_name(val: Any) -> str | None:
    """叶子值 → 符号名（Node 取 content/value，字符串原样）。"""
    if isinstance(val, str):
        return val or None
    if isinstance(val, Node):
        raw = getattr(val, "content", None) or getattr(val, "value", None)
        return raw if isinstance(raw, str) and raw else None
    return str(val) if val is not None else None


def _subtree_has(node: Node, marker: str) -> bool:
    """子树内是否出现指定节点名（如 `keyword.typedef` / `FuncSuffix`）。

    用 `Node.iter_children()`（引擎通用子节点迭代），"哪个标记代表 typedef/函数"由
    语言包 TOML 声明（见 `01_declarations.toml`）——本模块不含 C 语法知识。
    """
    if node.node_name == marker:
        return True
    return any(_subtree_has(child, marker) for child in node.iter_children())


def _declare(analyzer: Any, node: Node, name: str, kind: str) -> None:
    """登记一条 `analyze` 期符号（复用 `Scope.declare`；**不报诊断**）。

    与引擎 `symbol_declare` 原语的差别：同作用域重名时**静默跳过**（保持首见）而不报
    E001——本片纪律"产物只增不改既有行为"，不得因收集而新增诊断。
    """
    scope = getattr(analyzer, "_current_scope", None)
    if scope is None:
        return
    if name in scope.symbols:
        return
    attrs = {"phase": PHASE_ANALYZE, "decl_line": getattr(node, "_pos_line", None)}
    sym = scope.declare(name=name, kind=kind, decl_node=node, attrs=attrs)
    analyzer._all_symbols.append(sym)


def collect_declarator_site(analyzer: Any, node: Node, config: dict) -> None:
    """`site="declarator"`：声明符位（Declaration 的声明符表 / FuncDef / ParamDecl）。

    TOML 声明面（语言知识在配置）：
      `item_path`       声明项容器路径（Declaration 用 `declarators.items`；省略 = 节点自身）
      `name_path`       声明项内取名的路径（`declarator.direct.head.content`）
      `typedef_marker`  整条声明子树内出现即 typedef（`keyword.typedef`）
      `function_marker` 声明项子树内出现即函数名（`FuncSuffix`）
      `kind` / `typedef_kind` / `function_kind`  三类 kind 取值
    """
    items: list[Any]
    item_path = config.get("item_path")
    items = _walk(node, item_path) if item_path else [node]
    name_path = config.get("name_path", "")
    has_typedef = bool(
        config.get("typedef_marker") and _subtree_has(node, config["typedef_marker"])
    )
    fn_marker = config.get("function_marker")
    for item in items:
        if not isinstance(item, Node):
            continue
        names = [n for n in (_as_name(v) for v in _walk(item, name_path)) if n]
        if not names:
            continue
        if fn_marker and _subtree_has(item, fn_marker):
            kind = config.get("function_kind", KIND_FUNCTION)
        elif has_typedef:
            kind = config.get("typedef_kind", KIND_TYPEDEF)
        else:
            kind = config.get("kind", KIND_VARIABLE)
        for name in names:
            _declare(analyzer, item, name, kind)


def collect_named_site(analyzer: Any, node: Node, config: dict) -> None:
    """`site="named"`：名在节点属性上（标签 `tag` / 枚举常量 `name`）；缺属性 = 匿名，跳过。"""
    name_attr = config.get("name_attr", "")
    if not name_attr:
        return
    name = _as_name(getattr(node, name_attr, None))
    if name:
        _declare(analyzer, node, name, config.get("kind", KIND_VARIABLE))


# ── 后置产物（postpass 体） ──────────────────────────────────────────


def records_from_symbols(analyzer: Any) -> list[dict]:
    """`analyzer.all_symbols`（`Scope.declare` 产物）→ 产物记录表。

    `decl_order` = 收集序（遍历按 `iter_children()` 源序推进，故 ≈ 声明序）；
    `decl_line` 取 parser 挂在声明节点上的 `_pos_line`（无则 None）。
    """
    records: list[dict] = []
    for order, sym in enumerate(analyzer.all_symbols):
        scope = getattr(sym, "scope", None)
        attrs = getattr(sym, "attrs", {}) or {}
        records.append(
            {
                "name": sym.name,
                "kind": sym.kind,
                "scope": scope_path(scope),
                "scope_kind": getattr(scope, "kind", None),
                "decl_order": order,
                "decl_line": attrs.get("decl_line"),
                "phase": attrs.get("phase", PHASE_ANALYZE),
            }
        )
    return records


def _product_dict(analyzer: Any) -> dict:
    """analyze 期产物字典（记录表 + 元信息）。`build_product` / `product_from` 共用同一形状。"""
    return {
        "records": records_from_symbols(analyzer),
        "phases": [PHASE_ANALYZE],
        "default_typedef_bias": DEFAULT_TYPEDEF_BIAS,
        "scope_root": scope_path(getattr(analyzer, "root_scope", None)),
    }


def build_product(analyzer: Any, context: Any) -> None:
    """postpass：把 analyze 期符号表物化成只读产物写进 `context.extra[PRODUCT_KEY]`。

    只写 context：不改 AST、不报诊断（`produces` 与 `PRODUCT_KEY` 同名）。
    """
    context.extra[PRODUCT_KEY] = _product_dict(analyzer)


def product_from(analyzer: Any, context: Any = None) -> dict:
    """**读取入口**：取 analyze 期产物。

    `context` 省略时用 `analyzer._context`（`AnalysisTraversal` 的 context）；产物缺失
    （postpass 未注册/未跑）时**现场重建**同一形状，故消费方无需知道 postpass 是否执行过。
    ⚠ `ProjectChecker.check()` 的公开结果不含 `extra`（刻意的结果面收窄）——需要符号产物时
    直接用 `AnalysisTraversal`（复跑片段见 `grammar/c/README.md`「符号收集产物」节）。
    """
    ctx = context if context is not None else getattr(analyzer, "context", None)
    if ctx is not None:
        product = ctx.extra.get(PRODUCT_KEY)
        if isinstance(product, dict):
            return product
    return _product_dict(analyzer)


def two_phase_product(analyzer: Any, source: str, rules_dir: str, context: Any = None) -> dict:
    """两期合并产物：`records` = `pre_scan` + `analyze`（逐条带 `phase`），元信息同 analyze 产物。

    `source` 是**同一份源码文本**（预扫描在文本上跑，不依赖 AST）；用于分期对比：
    同名在两期都有记录时**两条都留**（`phases_for` 可判）。
    """
    base = product_from(analyzer, context)
    return {
        **base,
        "records": merge_phases(pre_scan_records(source, rules_dir), base["records"]),
        "phases": [PHASE_PRE_SCAN, PHASE_ANALYZE],
    }


# ── 查询 API（消费方唯一入口；勿直接读 records 猜语义） ──────────────


def pre_scan_records(source: str, rules_dir: str) -> list[dict]:
    """`phase="pre_scan"` 记录：调语言包声明的 `[lexer] pre_scan`（只读、无副作用）。

    ⚠ 预扫描是**粗收集**（平坦 / 首见归属 / 无声明序；引擎兜底正则还会带入少量
    非声明名——见 `grammar/c/base/_pre_scan.toml` 头注）：只作提示与分期对比，
    **不得**用于形态判定。
    """
    from lexer import load_pre_scan_config, pre_scan

    symbols = pre_scan(source, load_pre_scan_config(rules_dir))
    out: list[dict] = []
    for order, (name, kind) in enumerate(symbols.items()):
        out.append(
            {
                "name": name,
                "kind": kind,
                "scope": SCOPE_FILE_UNKNOWN,
                "scope_kind": None,
                "decl_order": None,  # 预扫描不给声明序（只保留首见）
                "decl_line": None,  # 亦不给位置
                "phase": PHASE_PRE_SCAN,
                "_pre_scan_seen_index": order,
            }
        )
    return out


def merge_phases(*record_lists: Iterable[dict]) -> list[dict]:
    """合并多期记录（同一位点两期都有 ⇒ 两条都留，供逐期对比）。"""
    merged: list[dict] = []
    for records in record_lists:
        merged.extend(records)
    return merged


def records_for(name: str, records: Sequence[dict]) -> list[dict]:
    """按名取记录（可能跨期/跨作用域多条）。"""
    return [r for r in records if r.get("name") == name]


def phases_for(name: str, records: Sequence[dict]) -> set[str]:
    """该名出现在哪些期（如 `{"pre_scan", "analyze"}`）。"""
    return {str(r.get("phase")) for r in records_for(name, records)}


def is_typedef(
    name: str,
    records: Sequence[dict],
    at_line: int | None = None,
    scope: str | None = None,
) -> bool:
    """该名在给定位置是否为 typedef 名；**无记录即 `DEFAULT_TYPEDEF_BIAS`（False）**。

    - 只看 `phase="analyze"` 记录（预扫描期无作用域/顺序，不作判定依据）；
    - `at_line` 给定时要求 `decl_line <= at_line`（先声明后使用；`decl_line` 缺失的记录不参与）；
    - `scope` 给定时**精确匹配**作用域路径（块内遮蔽/出块失效场景；前缀过滤由调用方自行筛）。
    """
    for rec in records_for(name, records):
        if rec.get("phase") != PHASE_ANALYZE or rec.get("kind") != KIND_TYPEDEF:
            continue
        if at_line is not None:
            line = rec.get("decl_line")
            if line is None or int(line) > at_line:
                continue
        if scope is not None and rec.get("scope") != scope:
            continue
        return True
    return False  # = DEFAULT_TYPEDEF_BIAS（"not typedef"）
