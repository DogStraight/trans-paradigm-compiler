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

from core.define import Node, marker_matches
from analyzer.scope import Scope, Symbol

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

# ── 声明位置派生视图（N1/N2，task-47）────────────────────────────────
#: 「声明位置」判定用到的节点名（包侧语言知识；先例 `SC_NODE_NAMES`）：
#: `FuncDef` 位的符号被声明进**它自己的**作用域（标准原语 `scope_enter` 先于自定义原语执行），
#: 对"文件域/声明位置"语义而言它的声明位置是**父作用域**；
#: `ParamDecl` 位的符号是**形参**（无 linkage、不参与文件域，原型形参当前落在 `<global>`）。
FUNC_DEF_NODE = "FuncDef"
PARAM_DECL_NODE = "ParamDecl"
#: 形参在派生视图里的 `decl_scope` 标签（**不是**真实作用域名：形参不占文件域/块声明位置）
PARAM_SCOPE_LABEL = "param"

#: **包声明的说明符分类**（C 语言知识；引擎不认识任何说明符名）：
#: 存储类说明符集合 ⊆ §6.7.1（含 c11/c23 增量注入的宿主节点名）；
#: 函数说明符集合 = §6.7.4（`inline` 核心 + c11 `_Noreturn`）。
SC_NODE_NAMES = frozenset(
    {"StorageClass", "ThreadLocalSpec", "ThreadLocalC23Spec", "ConstexprSpec"}
)
FS_NODE_NAMES = frozenset({"FuncSpec", "NoreturnSpec"})
#: `ConstexprSpec` 的共现规则**未经核实**（C23 原文未见；权威转述与示例反证"须与 static/extern 共现"），
#: 故 CSC001/CSC002 对它**保守放行**（宁可漏报不误报）：不计入"至多一个存储类"的计数、也不算"其他存储类"。
CSC_PERMISSIVE_SPECS = frozenset({"ConstexprSpec"})


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


def _subtree_has(node: Node, marker: Any) -> bool:
    """子树内是否出现指定标记——**跨两种 AST 形态**判定（薄封装）。"""

    # 实现已上移到**引擎通用面** `core.define.marker_matches`：normalize 会把
    # `keyword.*` / `symbol.*` / `literal.*` 的 token 叶子抽成父节点的**字符串属性值**
    # （`keyword.typedef` → `StorageClass.base = "typedef"`），只按节点名判会在生产口径下
    # 恒不命中——这是引擎行为、服务所有语言包，故不在本包重复实现（本包保留旧名只为
    # `collect_declarator_site` 调用点可读；语义与引擎面完全一致）。
    return marker_matches(node, marker)


def decl_position(node: Node | None, scope: Scope | None) -> tuple[str, bool, bool]:
    """一条声明的**声明位置**（N1/N2 的单一判定点）：`(decl_scope, is_file_decl, is_param)`。

    ⚠ **派生视图是"声明位置"的唯一入口**（task-47 拍板 ④）：`record["scope"]` 是**分析作用域**
    （语义不变），凡"它在哪声明 / 算不算文件域声明"的问题一律走本函数 / `declaration_view()`。

    判定（当前符号基座事实；两处**已登记偏差**见 `grammar/c/README.md`「符号基座两处错位」）：
      · `ParamDecl` 位 ⇒ `("param", False, True)`——形参无 linkage、**不是**文件域声明
        （原型形参当前落在 `<global>`，与文件域对象声明同形，故必须在此排除）；
      · `FuncDef` 位 ⇒ 取**父作用域**（函数定义符号被声明进自己的作用域）：
        `(scope_path(parent), parent 是根作用域, False)`；
      · 其余 ⇒ `(scope_path(scope), scope 是根作用域, False)`。
    """
    if getattr(node, "node_name", None) == PARAM_DECL_NODE:
        return PARAM_SCOPE_LABEL, False, True
    if getattr(node, "node_name", None) == FUNC_DEF_NODE:
        parent = getattr(scope, "parent", None)
        if parent is None:
            return scope_path(scope), False, False
        return scope_path(parent), getattr(parent, "parent", None) is None, False
    return scope_path(scope), scope is not None and getattr(scope, "parent", None) is None, False


def _declare(
    analyzer: Any, node: Node, name: str, kind: str, attrs: dict | None = None
) -> None:
    """登记一条 `analyze` 期符号（复用 `Scope.declare`；**不报诊断**）。

    与引擎 `symbol_declare` 原语的差别：同作用域重名时**不报 E001**——本片纪律
    "产物只增不改既有行为"，不得因收集而新增诊断。

    ⚠ **重名仍要进 `records`（声明历史）**：作用域查找语义保持"首见"（`scope.symbols`
    不覆盖），但 `analyzer._all_symbols` 保留**每一条声明**——P4 查询要按
    `(decl_order, line, column)` 判"**最近声明**遮蔽"与"同作用域重声明"
    （`typedef int t; int t;` 与 `typedef int t; typedef int t;` 只有保留历史才可区分；
    折叠成首条会让 `int t` 后的使用点被误判为 typedef）。

    `attrs`：额外捕获（说明符摘要 / 是否函数 / 有无初始化器 / 声明起点）——供 L1 检查
    组件读取（**不改 `decl_node` 语义**，见 task-36 拍板 ④）。

    本函数另外把**声明位置三元组**（`decl_scope` / `is_file_decl` / `is_param`，见
    `decl_position`）写入 `attrs`（N2；先例 = 作者对 `phase` 落 attrs 的裁决）——
    **不进 P1 产物**，故产物形状/语义零变化（task-47 判据 2）。
    """
    scope = getattr(analyzer, "_current_scope", None)
    if scope is None:
        return
    merged = {"phase": PHASE_ANALYZE, "decl_line": getattr(node, "_pos_line", None)}
    if attrs:
        merged.update(attrs)
    decl_scope, is_file_decl, is_param = decl_position(node, scope)
    merged.setdefault("decl_scope", decl_scope)
    merged.setdefault("is_file_decl", is_file_decl)
    merged.setdefault("is_param", is_param)
    if name in scope.symbols:
        # 同作用域重声明：查找语义不变（首见），仅补一条**声明历史**记录
        sym = Symbol(name=name, kind=kind, decl_node=node, scope=scope, attrs=merged)
    else:
        sym = scope.declare(name=name, kind=kind, decl_node=node, attrs=merged)
    analyzer._all_symbols.append(sym)


def collect_declarator_site(analyzer: Any, node: Node, config: dict) -> None:
    """`site="declarator"`：声明符位（Declaration 的声明符表 / FuncDef / ParamDecl）。

    TOML 声明面（语言知识在配置）：
      `item_path`       声明项容器路径（Declaration 用 `declarators.items`；省略 = 节点自身）
      `name_path`       声明项内取名的路径；**字符串或候选路径列表**（按序试，首个命中即用）——
                        包装规则（`TypedefDeclarator` 等）不透出 `direct` 属性，故函数/形参位
                        需要 `declarator.direct.head.content` 与
                        `declarator.declarator.direct.head.content` 两条候选；不能靠"并联属性"
                        透出 `direct`：同一子树会被 `iter_children` 走两遍（重复符号记录 +
                        TAG001 假阳性，循环 #44 对抗审计实测）。
      `typedef_marker`  整条声明子树内出现即 typedef（`keyword.typedef`）
      `function_marker` 声明项子树内出现即函数名（`FuncSuffix`）
      `kind` / `typedef_kind` / `function_kind`  三类 kind 取值
    """
    items: list[Any]
    item_path = config.get("item_path")
    items = _walk(node, item_path) if item_path else [node]
    name_path = config.get("name_path", "")
    name_paths = [name_path] if isinstance(name_path, str) else list(name_path or [])
    if not name_paths:
        name_paths = [""]
    has_typedef = bool(
        config.get("typedef_marker") and _subtree_has(node, config["typedef_marker"])
    )
    fn_marker = config.get("function_marker")
    # 说明符摘要（声明级，一次算好；检查组件读符号 attrs 判定存储类约束）
    decl_attrs = _decl_attrs(node, spec_capture(node, config))
    for item in items:
        if not isinstance(item, Node):
            continue
        names: list[str] = []
        for path in name_paths:
            names = [n for n in (_as_name(v) for v in _walk(item, path)) if n]
            if names:
                break
        if not names:
            continue
        fn_kind = config.get("function_kind", KIND_FUNCTION)
        if fn_marker and _subtree_has(item, fn_marker):
            kind = fn_kind
        elif has_typedef:
            kind = config.get("typedef_kind", KIND_TYPEDEF)
        else:
            kind = config.get("kind", KIND_VARIABLE)
        # `is_function`：声明符带函数标记（函数声明）**或**规则声明 kind 即函数（`FuncDef` 位）
        item_attrs = {
            **decl_attrs,
            "is_function": kind == fn_kind,
            "has_init": getattr(item, "init", None) is not None,
        }
        for name in names:
            _declare(analyzer, item, name, kind, item_attrs)


def collect_named_site(analyzer: Any, node: Node, config: dict) -> None:
    """`site="named"`：名在节点属性上（标签 `tag` / 枚举常量 `name`）；缺属性 = 匿名，跳过。

    额外采集（`tag_capture`，S1-a）：tag **种类**与**有无体**——判据要区分"定义"与"引用/前向声明"
    （§6.7.2.3：可见声明存在时该类型说明符不重声明 tag），故二者必须进 attrs。
    """
    name_attr = config.get("name_attr", "")
    if not name_attr:
        return
    name = _as_name(getattr(node, name_attr, None))
    if name:
        _declare(
            analyzer, node, name, config.get("kind", KIND_VARIABLE), _named_attrs(node, config)
        )


def _named_attrs(node: Node, config: dict) -> dict:
    """`site="named"` 的采集结果（声明起点 + `tag_capture`）。

    `tag_capture` 声明键（全在 TOML；包内不含语言名）：
      `kind_path`    取种类子节点（`StructOrUnion.base` → `struct`/`union`）
      `body_path`    取"体"子节点；存在 ⇒ `has_body=True`（定义），缺失 ⇒ 引用/前向声明
      `complete_path` 取"**无体也完整**"的声明信号（C23 固定底层类型枚举：`enum E : int;`
                     按 §6.7.2.2 总是完整）⇒ `has_complete_type=True`
      `default_kind` 无 `kind_path` 时的字面种类（enum 说明符没有种类子节点）
    """
    attrs: dict = {
        "decl_start_line": getattr(node, "_pos_line", None),
        "decl_start_col": getattr(node, "_pos_col", None),
    }
    capture = config.get("tag_capture") or {}
    tag_kind: str | None = None
    kind_path = capture.get("kind_path")
    if kind_path:
        for val in _walk(node, kind_path):
            base = getattr(val, "base", None)
            tag_kind = base if isinstance(base, str) and base else getattr(val, "node_name", None)
            if tag_kind:
                break
    if not tag_kind:
        default_kind = capture.get("default_kind")
        tag_kind = default_kind if isinstance(default_kind, str) and default_kind else None
    if tag_kind:
        attrs["tag_kind"] = tag_kind
    body_path = capture.get("body_path")
    if body_path:
        attrs["has_body"] = any(isinstance(v, Node) for v in _walk(node, body_path))
    complete_path = capture.get("complete_path")
    if complete_path:
        attrs["has_complete_type"] = any(
            isinstance(v, Node) for v in _walk(node, complete_path)
        )
    return attrs


# ── 说明符 capture（包侧；CSC 检查的输入面） ───────────────────────


def _spec_short(spec: Node) -> str:
    """说明符节点 → 短串（normalize 后取 `base`；无则回落节点名）。

    实测形状：`StorageClass{base="static"}`、`ThreadLocalSpec{base="_Thread_local"}`、
    `ThreadLocalC23Spec{base="thread_local"}`、`ConstexprSpec{base="constexpr"}`、
    `FuncSpec{base="inline"}`、`NoreturnSpec{base="_Noreturn"}`。
    """
    base = getattr(spec, "base", None)
    if isinstance(base, str) and base:
        return base
    return spec.node_name


def _spec_nodes(node: Node, config: dict) -> list[Node]:
    """按 TOML 声明的路径取该声明的**全部说明符节点**。

    路径来自 `[Rule.analyzer.c_symbol_collect] capture = { specs = "specs", specs_rest = "rest" }`：
    `specs` = 首个说明符；`rest` = 其余（`SpecRest` 节点或列表，其 `.spec` 才是说明符节点）。
    """
    capture = config.get("capture") or {}
    out: list[Node] = []
    for key in ("specs", "specs_rest"):
        path = capture.get(key)
        if not path:
            continue
        for val in _walk(node, path):
            if not isinstance(val, Node):
                continue
            inner = getattr(val, "spec", None)
            out.append(inner if isinstance(inner, Node) else val)
    return out


def spec_capture(node: Node, config: dict) -> dict:
    """声明节点的说明符摘要 → 符号 attrs（检查组件按此判定）。

    返回：`{"sc": [...存储类短串...], "fs": [...函数说明符短串...], "spec_other": [...]}`。
    分类用包侧常量（`SC_NODE_NAMES` / `FS_NODE_NAMES`）；未分类的说明符进 `spec_other`（取证用，不判定）。
    """
    sc: list[str] = []
    fs: list[str] = []
    other: list[str] = []
    for spec in _spec_nodes(node, config):
        short = _spec_short(spec)
        if spec.node_name in SC_NODE_NAMES:
            sc.append(short)
        elif spec.node_name in FS_NODE_NAMES:
            fs.append(short)
        else:
            other.append(short)
    return {"sc": sc, "fs": fs, "spec_other": other}


def _decl_attrs(node: Node, capture: dict) -> dict:
    """声明级 attrs（声明起点身份：多声明符去重的键）。"""
    return {
        "decl_start_line": getattr(node, "_pos_line", None),
        "decl_start_col": getattr(node, "_pos_col", None),
        **capture,
    }


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


def declaration_view(analyzer: Any) -> list[dict[str, Any]]:
    """**声明位置派生视图**（N1）：「这条声明在哪声明 / 算不算文件域声明」的唯一入口。

    ⚠ **纪律（task-47 拍板 ④）**：`product_from()["records"]` 的 `scope`/`scope_kind` 是
    **分析作用域**（P1 公开产物，语义不变、**不得**在此改）；凡声明位置问题（文件域判定、
    形参排除、函数定义归属）一律走本视图——避免"两套真相"漂移。

    字段：
      `name`/`kind`/`decl_line`/`decl_order`/`phase`  ← 与产物记录同源（便于对照）
      `scope`/`scope_kind`                          ← 原分析作用域（**语义不变**，仅供诊断/取证）
      `decl_scope`                                  ← **声明位置**：FuncDef 位取父作用域；
                                                       形参位为 `"param"`；其余同 `scope`
      `is_file_decl`                                ← 是否**文件域声明**（形参位恒 False）
      `is_param`                                    ← 是否形参（无 linkage、不参与文件域）

    处置的两处**当前仍成立的基座偏差**见 `grammar/c/README.md`「符号基座两处错位」。
    attrs 缺三元组时（例如引擎 `symbol_declare` 建的符号）**现场用 `decl_position` 推导**。
    """
    view: list[dict[str, Any]] = []
    for order, sym in enumerate(getattr(analyzer, "all_symbols", None) or []):
        scope = getattr(sym, "scope", None)
        attrs = getattr(sym, "attrs", None) or {}
        node = getattr(sym, "decl_node", None)
        if "decl_scope" in attrs and "is_param" in attrs and "is_file_decl" in attrs:
            decl_scope = str(attrs.get("decl_scope"))
            is_param = bool(attrs.get("is_param"))
            is_file_decl = bool(attrs.get("is_file_decl"))
        else:
            decl_scope, is_file_decl, is_param = decl_position(node, scope)
        view.append(
            {
                "name": sym.name,
                "kind": sym.kind,
                "decl_scope": decl_scope,
                "is_file_decl": is_file_decl,
                "is_param": is_param,
                "scope": scope_path(scope),
                "scope_kind": getattr(scope, "kind", None),
                "decl_line": attrs.get("decl_line"),
                "decl_order": order,
                "phase": attrs.get("phase", PHASE_ANALYZE),
            }
        )
    return view


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
