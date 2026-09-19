"""boundary.py — 结构边界扫描器

对 token 流做单次遍历，追踪结构边界（module/begin/end/ifdef/else/endif/case 等），
为每条行产出其在 scope 栈中的上下文位置。

核心能力：
  - 块起止符追踪（begin/end, module/endmodule, generate/endgenerate, case/endcase 等）
  - 从语法规则自动推导 token → ScopeKind 映射
  - ifdef/else/endif 分支感知（分支内独立追踪，endif 处收敛校验）
  - 行级别 scope 快照 + 块头/块尾标记 + 行内注释标记

Doc: grammar/verilog/plugins/formatter/README.md（边界扫描）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from lexer import Lexer

from core.define import GrammarRule
from core.token_protocol import KEYWORD_PREFIX, SYMBOL_PREFIX, macro_type

# ── BlockTokenMap ──


@dataclass
class BlockTokenMap:
    """由语法规则构建的块边界映射。"""

    openers: set[str] = field(default_factory=set)
    closers: set[str] = field(default_factory=set)
    ifdef_set: set[str] = field(default_factory=set)
    scope_kind_map: dict[str, "ScopeKind"] = field(default_factory=dict)
    stmt_headers: set[str] = field(default_factory=set)
    stmt_end_tokens: set[str] = field(default_factory=set)
    """语句结束 token（分号类）：从语句规则 production 里的 *.semicolon 推导。"""
    decl_headers: set[str] = field(default_factory=set)
    """声明头 token（input/output/reg/wire/parameter...）：声明行不参与多行续行。"""
    stmt_headers: set[str] = field(default_factory=set)
    """控制流语句头 token（if/for/else 等，从 is_statement 规则推导）。

    用于识别"无 begin 的单语句体"（如 `if (X)` 后接单语句）的悬挂缩进。
    具体关键字一律由规则推导，不在此硬编码。
    """


def _resolve_first_tokens(
    tree: dict, feat: dict | None, visited: set[str] | None = None
) -> set[str]:
    """递归解析 feature 的起始 token，跟踪 call 链。"""
    if feat is None:
        return set()
    if visited is None:
        visited = set()
    typ = feat.get("type")
    if typ == "token":
        tt = feat.get("token_type", "")
        if "|" in tt:
            return set(tt.split("|"))
        return {tt}
    if typ == "call":
        name = feat.get("name", "")
        if name in visited or name not in tree:
            return set()
        visited.add(name)
        info = tree[name]
        prods = info.get("prods", [])
        if not prods:
            return set()
        return _resolve_first_tokens(tree, prods[0], visited)
    if typ == "choice":
        result: set[str] = set()
        for alt in feat.get("alternatives", []):
            result |= _resolve_first_tokens(tree, alt, set(visited))
        return result
    if typ == "seq":
        items = feat.get("items", [])
        if items:
            return _resolve_first_tokens(tree, items[0], visited)
        return set()
    if typ in ("repeat", "plus"):
        elem = feat.get("elem")
        if elem:
            return _resolve_first_tokens(tree, elem, visited)
        return set()
    if typ == "optional":
        return set()
    return set()


def _kind_from_name(name: str) -> "ScopeKind | None":
    """规则 analyzer.scope.kind 的字符串（如 "module"/"for_loop"）→ ScopeKind 枚举。

    只接受 formatter 关心的结构边界类别；其它 kind（如类型系统的 "type"）
    不属于结构边界，返回 None（调用方跳过，不进入 scope_kind_map）。
    """
    try:
        return ScopeKind[name.strip().upper()]
    except (KeyError, AttributeError):
        return None


def _same_line_next(tokens: list, idx: int, trivia: frozenset[str]) -> bool:
    """`{` 后同行还有非 trivia 内容 → 表达式花括号（concat/replicate）。

    行尾 `{`（块开，如 `type spi {` / `impl [m] (...) {`）后是换行；
    行中 `{`（表达式，如 `assign x = {a, b};`）后是表达式内容。
    """
    for t in tokens[idx + 1 :]:
        if t.type in trivia:
            if t.type == "newline":
                return False
            continue
        return True
    return False


# ── 边界 token 集合（由语法规则自动构建）──


def _tail_keyword_tokens(info: dict) -> set[str]:
    """规则 production 末尾的 keyword.* 字面 token（隐式块终结符）。

    非 is_block 规则（如 CaseStmt/EventWaitStmt）的隐式块结束关键字
    （endcase/endfunction/endtask 等）在 production 末尾字面 token 里，
    从结构推导而非手写 end_case 字段（end_case 已移除）。
    """
    prods = info.get("prods", [])
    if not prods:
        return set()
    result: set[str] = set()
    last = prods[-1]
    if isinstance(last, dict) and last.get("type") == "token":
        tt = last.get("token_type", "")
        if tt.startswith(KEYWORD_PREFIX) and "|" not in tt:
            result.add(tt)
    return result


def _collect_call_names(feat, out: set[str]) -> None:
    """递归收集 feature 树里的 @call 引用名（choice/seq/repeat 内部也要）。"""
    if isinstance(feat, dict):
        _collect_dict_calls(feat, out)
    elif isinstance(feat, str) and feat.startswith("@"):
        out.add(feat[1:])


def _collect_dict_calls(feat: dict, out: set[str]) -> None:
    """字典 feature：自身的 @call 名 + 递归各子 feature。"""
    if feat.get("type") == "call":
        out.add(feat.get("name", ""))
    for child in _call_children(feat):
        _collect_call_names(child, out)


def _call_children(feat: dict) -> list:
    """字典 feature 的子位：alternatives/items 列表各项 + elem 单值。

    elem 为列表时原样返回（调用方对非 dict 非 str 的输入不做处理）。
    """
    children: list = []
    for key in ("alternatives", "items"):
        v = feat.get(key)
        if isinstance(v, list):
            children.extend(v)
    elem = feat.get("elem")
    if isinstance(elem, (dict, list)):
        children.append(elem)
    return children


def _collect_block_rule_bounds(
    tree: dict, openers: set[str], closers: set[str]
) -> None:
    """第一轮：`is_block = True` 的规则 → openers/closers（含匿名块父规则）。"""
    from linter.grammar_slicer import get_start_tokens

    anon_blocks: set[str] = set()
    for name, info in tree.items():
        if not info.get("is_block"):
            continue
        be = info.get("block_end") or ""
        if be:
            closers.add(be)
        prods = info.get("prods", [])
        if not prods:
            anon_blocks.add(name)
        else:
            openers |= get_start_tokens(prods)

    # 匿名块的父规则 → 找 opener/closer
    seen_parents: set[str] = set()
    for name, info in tree.items():
        prods = info.get("prods", [])
        if not prods or name in seen_parents:
            continue
        for feat in prods:
            if feat.get("type") != "call":
                continue
            if feat.get("name") in anon_blocks:
                openers |= get_start_tokens(prods)
                for f in reversed(prods):
                    if f.get("type") == "token":
                        closers.add(f["token_type"])
                        break
                seen_parents.add(name)
                break


def _collect_end_keyword_bounds(
    tree: dict, openers: set[str], closers: set[str]
) -> None:
    """第二轮：production 末尾关键字终结符的隐式块（case/function/task 等）。

    终结符从规则 production 推导（非 is_block 规则末尾 keyword.* 字面 token），
    不硬编码 endcase/endfunction 等具体名（end_case 已移除）。
    """
    end_markers = frozenset(
        tok
        for info in tree.values()
        if isinstance(info, dict) and not info.get("is_block")
        for tok in _tail_keyword_tokens(info)
    )
    for name, info in tree.items():
        if info.get("is_block"):
            continue  # 第一轮已处理
        ec_tail = _tail_keyword_tokens(info)
        # 只关注有明确关键字终结符的规则
        if not ec_tail or not ec_tail & end_markers:
            continue
        prods = info.get("prods", [])
        if not prods:
            continue
        tokens = _resolve_first_tokens(tree, prods[0])
        if tokens:
            openers |= tokens
            closers |= ec_tail & end_markers  # 只取关键字终结符


def _build_scope_kind_map(
    rules: dict, tree: dict, openers: set[str], closers: set[str]
) -> dict[str, ScopeKind]:
    """token → ScopeKind（从规则 analyzer.scope.kind 推导），并把入口/终结 token 归入 opener/closer。

    结构类别是规则自身的语义声明，非 formatter 单独映射表。副作用：向
    `openers` / `closers` 补入带配对结束符的块入口与终结符（与推导同源）。
    """
    from linter.grammar_slicer import get_start_tokens

    scope_kind_map: dict[str, ScopeKind] = {}
    for name, rule in rules.items():
        if not isinstance(rule, GrammarRule):
            continue
        analyzer = getattr(rule, "analyzer", None)
        if not isinstance(analyzer, dict):
            continue
        scope_meta = analyzer.get("scope")
        if not isinstance(scope_meta, dict):
            continue
        kind_name = scope_meta.get("kind")
        if not kind_name:
            continue
        kind = _kind_from_name(kind_name)
        if kind is None:
            continue  # 非结构边界 kind（如类型系统的 "type"），不进入 scope_kind_map
        info = tree.get(name, {}) or {}
        # 只用 slicer 解析后的 prods（内容部分）。不能回退 rule.prods——方案 B
        # 下块规则 production 保留完整（字符串列表），与 parsed dict 混用会炸；
        # 且 GenerateBlock 等无内容 production 的块规则本就走空 prods 分支。
        prods = info.get("prods") or []
        # 有配对结束符（block_end / production 尾关键字终结符 / 块类别）的规则
        # 才是"块"；always/initial/if/for 等语句头（体是 begin 块或单语句，
        # 无关键字终结符）不在块类别，其 first token 不进 openers。
        bs = getattr(rule, "block_start", "") or ""
        be = getattr(rule, "block_end", "") or ""
        ec_kw = _tail_keyword_tokens(info)
        has_pair = bool(be) or bool(ec_kw) or kind in _PAIRED_BLOCK_KINDS
        if has_pair and not be:
            # 无 block_end 的块（如 CaseStmt：endcase 在 production 尾）——
            # 取 production 尾字面 token 作配对 closer
            prods_full = (
                getattr(rule, "production", None) or getattr(rule, "prods", None) or []
            )
            if (
                prods_full
                and isinstance(prods_full[-1], str)
                and not prods_full[-1].startswith("@")
            ):
                be = prods_full[-1]
        # first tokens → kind（块类规则的入口 token 才是 opener）
        tokens = _resolve_first_tokens(tree, prods[0]) if prods else set()
        if not tokens:
            tokens = get_start_tokens(prods)
        for tok in tokens:
            scope_kind_map.setdefault(tok, kind)
            if has_pair and isinstance(tok, str) and tok.startswith(KEYWORD_PREFIX):
                openers.add(tok)
        # block_start / block_end → kind（opener / closer）
        if bs:
            scope_kind_map.setdefault(bs, kind)
            if isinstance(bs, str) and bs.startswith(KEYWORD_PREFIX):
                openers.add(bs)
        if be:
            scope_kind_map.setdefault(be, kind)
            if isinstance(be, str) and be.startswith(KEYWORD_PREFIX):
                closers.add(be)
        # production 尾关键字终结符 → kind（closer：语句结束符如 endcase/endmodule）
        for e in ec_kw:
            if isinstance(e, str) and e.startswith(KEYWORD_PREFIX):
                scope_kind_map.setdefault(e, kind)
                closers.add(e)
    return scope_kind_map


def _collect_stmt_headers(
    tree: dict, openers: set[str], closers: set[str]
) -> set[str]:
    """控制流语句头 token 集（体可为单语句 → 悬挂缩进）。

    规则条件：体内引用语句/块（@Stmt/@Statement/@BeginEnd/@ElseChain）。不要求
    is_statement：else 系列规则（ElseBranch/ElseIfStmt）未标 is_statement，但
    语义上是语句头。具体关键字一律由规则推导，不在此硬编码。已作块 openers/
    closers 的不重复。
    """
    from linter.grammar_slicer import get_start_tokens

    stmt_headers: set[str] = set()
    for name, info in tree.items():
        if not isinstance(info, dict):
            continue
        prods = info.get("prods", [])
        if not prods:
            continue
        refs: set[str] = set()
        for f in prods:
            _collect_call_names(f, refs)
        # 体内引用语句/块（@Stmt/@Statement/@BeginEnd/@ElseChain）→ 控制流，
        # 体可为单语句（if/for/else/while/always 等），需要悬挂缩进
        if not (refs & {"Stmt", "Statement", "BeginEnd", "ElseChain"}):
            continue
        stmt_headers |= get_start_tokens(prods)
    # 只保留关键字类（控制流语句头都是关键字：if/for/else/always 等），
    # 排除符号类 first token（如 `@` 事件控制、`;` 空语句——它们不是语句头）
    stmt_headers = {t for t in stmt_headers if t.startswith(KEYWORD_PREFIX)}
    # 已作块 openers/closers 的（case/generate/function/task/module 等）不重复
    stmt_headers -= openers
    stmt_headers -= closers
    return stmt_headers


def _collect_stmt_end_tokens(tree: dict) -> set[str]:
    """语句结束 token（分号类）：从规则 production 里的 *.semicolon 推导。

    用于识别 if/for 单行体（body 同行，如 `if (X) stmt;`）——行尾分号表示
    语句头在本行已结束（语言知识外部化，不硬编码分号）。
    """
    stmt_end_tokens: set[str] = set()
    for info in tree.values():
        if not isinstance(info, dict):
            continue
        for f in info.get("prods", []):
            tt = f.get("token_type") if isinstance(f, dict) else f
            if isinstance(tt, str) and tt.endswith(".semicolon"):
                stmt_end_tokens.add(tt)
    return stmt_end_tokens


def _collect_decl_headers(rules: dict, tree: dict) -> set[str]:
    """声明头 token：有 analyzer.symbol.kind 的声明规则的 first token。

    （input/output/reg/wire/localparam...）声明行不是语句（module 体内 ifdef 的
    端口声明等），不参与多行续行。
    """
    from linter.grammar_slicer import get_start_tokens

    decl_headers: set[str] = set()
    for name, rule in rules.items():
        if not isinstance(rule, GrammarRule):
            continue
        analyzer = getattr(rule, "analyzer", None)
        if not isinstance(analyzer, dict):
            continue
        symbol_meta = analyzer.get("symbol")
        if not isinstance(symbol_meta, dict) or not symbol_meta.get("kind"):
            continue
        info = tree.get(name, {}) or {}
        prods = info.get("prods") or []
        if not prods:
            continue
        decl_headers |= get_start_tokens(prods)
    return {t for t in decl_headers if t.startswith(KEYWORD_PREFIX)}


def build_block_tokens(rules: dict) -> BlockTokenMap:
    """从语法规则构建边界 token 集合。

    自动推导：
      - is_block = True 的规则 → 开/闭 token 直接收集（block_start/block_end）
      - production 末尾有 keyword.* 字面 token 的规则（如 case/endcase）→
        作为隐式 scope 的终结符（从结构推导，end_case 已移除）
      - call 链递归解析（如 @CaseKeyword → keyword.case|casex|casez）
      - 每个 opener token 自动关联 ScopeKind

    Returns:
        BlockTokenMap 包含 openers / closers / ifdef_set / scope_kind_map
    """
    # 有配对结束符的块类别见模块级 `_PAIRED_BLOCK_KINDS`（判定 has_pair 用）
    from linter.grammar_slicer import build_slice_tree

    tree = build_slice_tree(rules)
    openers: set[str] = set()
    closers: set[str] = set()

    # ── 1. is_block 规则（含匿名块父规则）──
    _collect_block_rule_bounds(tree, openers, closers)
    # ── 2. production 尾关键字终结符的隐式块（case/function/task 等）──
    _collect_end_keyword_bounds(tree, openers, closers)

    # ── 3. token → ScopeKind（同时把块入口/终结符归入 openers/closers）──
    scope_kind_map = _build_scope_kind_map(rules, tree, openers, closers)

    ifdef_set = {
        macro_type("ifdef"),
        macro_type("ifndef"),
        macro_type("else"),
        macro_type("elsif"),
        macro_type("endif"),
    }

    # ── 4. 语句头 token（无 begin 的单语句体悬挂缩进）──
    stmt_headers = _collect_stmt_headers(tree, openers, closers)

    # ── 5. 语句结束 token（分号类）──
    stmt_end_tokens = _collect_stmt_end_tokens(tree)

    # ── 6. 声明头 token ──
    decl_headers = _collect_decl_headers(rules, tree)

    return BlockTokenMap(
        openers=openers,
        closers=closers,
        ifdef_set=ifdef_set,
        scope_kind_map=scope_kind_map,
        stmt_headers=stmt_headers,
        stmt_end_tokens=stmt_end_tokens,
        decl_headers=decl_headers,
    )


# ── scope 节点 ──


class ScopeKind(Enum):
    ROOT = auto()
    MODULE = auto()
    BLOCK = auto()
    FUNCTION = auto()
    TASK = auto()
    GENERATE = auto()
    CASE = auto()
    ALWAYS = auto()
    INITIAL = auto()
    FOR_LOOP = auto()
    IFDEF_BRANCH = auto()


# 有配对结束符的块类别（结构类别语义，非具体关键字）——`_build_scope_kind_map`
# 判定 has_pair 用。定义在 ScopeKind 之后：模块级名字在调用时才解析。
_PAIRED_BLOCK_KINDS = frozenset(
    {
        ScopeKind.MODULE,
        ScopeKind.BLOCK,
        ScopeKind.CASE,
        ScopeKind.GENERATE,
        ScopeKind.FUNCTION,
        ScopeKind.TASK,
    }
)


@dataclass
class ScopeNode:
    kind: ScopeKind
    name: str = ""
    token_line: int = 0


@dataclass
class ScopeBranch:
    """ifdef 的单个分支，维护独立的 scope 栈快照。"""

    condition: str = ""
    openers: list[ScopeNode] = field(default_factory=list)
    extra_openers: list[ScopeNode] = field(default_factory=list)


# ── 行上下文 ──


@dataclass
class LineContext:
    line_number: int
    text: str
    scope_path: list[ScopeKind] = field(default_factory=list)
    scope_depth: int = 0
    in_ifdef: bool = False
    ifdef_condition: str = ""

    # --- 新增元数据 ---
    scope_kind_stack: list[ScopeKind] = field(default_factory=list)
    """每层 scope 的 kind（不含 ROOT），与 scope_path 同步。"""
    block_header_of: ScopeKind | None = None
    """本行是哪个 ScopeKind 的块头（如 FUNCTION, CASE）。"""
    block_footer_of: ScopeKind | None = None
    """本行是哪个 ScopeKind 的块尾（如 endcase, endfunction 等）。"""
    has_trailing_comment: bool = False
    """本行是否包含行内 // 注释。"""
    is_case_item: bool = False
    """本行是否是 case/default 分支行。"""
    single_stmt_header: bool = False
    """本行是无 begin 的单语句头（如 `if (X)` / `for (...)`），下一行是其单语句体。"""
    is_else_header: bool = False
    """本行行首是 else（else 链行），与 if/end 对齐、不悬挂缩进。"""
    multi_line_cont: bool = False
    """本行是多行语句的续行（语句头在前一行，本行无分号继续）。"""
    multi_header_line: int = 0
    """续行所属多行语句的语句头行号（1-based），续行缩进相对它 +1。"""
    multi_extra: bool = False
    """续行额外 +1（语句头行尾是 `=` 连续赋值，三目链续行 ref 用 +2）。"""
    port_list_end: bool = False
    """本行是模块端口列表结束行（`);`），缩进对齐模块头（0 级）。"""
    is_directive: bool = False
    """本行是预处理指令（`ifdef/`define 等，从 token 配置推导）。wrap 区分
    指令不折 vs 宏调用语句（`LUI: $display(...)`，含 `(`）可折。"""
    is_comment_cont: bool = False
    """本行是**跨行块注释**内部的段（非首行）——注释自带版式（` * ` 与 `/*`
    对齐），缩进 pass 不按 scope_depth 重算，而是随注释首行整体平移。"""


# ── 边界扫描器 ──


# ── 扫描状态（`_scan_tokens` 的行累加量收拢为单一对象）──


@dataclass
class _ScanState:
    """`BoundaryScanner` 单次扫描的行累加状态。

    原先是 `_scan_tokens` 里的 16 个局部量，被注释/换行/内容三块共享读写——
    收拢成对象后才能把三块拆成独立方法（拆后各方法只改 `state`，不靠参数表）。
    字段语义见各字段行尾注释与原实现（本轮纯搬移，未改语义）。
    """

    contexts: list[LineContext]
    scope_path: list[ScopeNode]
    ifdef_branches: list[ScopeBranch]
    line_buf: list[str] = field(default_factory=list)
    line_num: int = 1
    line_has_comment: bool = False
    pending_block_header: ScopeKind | None = None
    pending_block_footer: ScopeKind | None = None
    pending_case_item: bool = False
    pending_stmt_header: bool = False
    pending_is_else: bool = False
    pending_line_comment: bool = False
    # 多行块注释末段（含闭合标记）落行时继承 is_comment_cont
    pending_comment_cont: bool = False
    in_port_list: bool = False
    multi_active: bool = False
    multi_header_line: int = 0
    multi_depth_extra: int = 0
    line_first_token: str | None = None
    last_line_nontrivia: str | None = None
    # 最近的 case 深度（识别 case 分支项）
    case_depth: int = -1
    # 表达式花括号（concat/replicate）未闭合计数：表达式 `{` 不入块栈
    brace_expr_depth: int = 0


class BoundaryScanner:
    """单次 token 流遍历 → 为每行产出 LineContext。

    ifdef/else/endif 分支各自维护独立的 scope 栈：
      1. 进入 ifdef 时快照当前 scope_path → branch.openers
      2. 分支内 opener 记入 branch.extra_openers
      3. 每个分支结束后（else/elsif/endif），scope_path 恢复为快照
      4. endif 处校验所有分支的栈收敛到同一深度
    """

    _TRIVIA = frozenset(
        {"newline", "space.indent", "space.dedent", "space.fold", "comment"}
    )
    _COMMENT_LINE = frozenset({"comment"})

    def __init__(self, rules: dict, lexer: Lexer):
        self.lexer = lexer
        self.token_map = build_block_tokens(rules)
        self.openers = self.token_map.openers
        self.closers = self.token_map.closers
        self.ifdef_set = self.token_map.ifdef_set
        self.scope_kind_map = self.token_map.scope_kind_map
        self.stmt_headers = self.token_map.stmt_headers
        self.stmt_end_tokens = self.token_map.stmt_end_tokens
        self.decl_headers = self.token_map.decl_headers
        # 闭合括号 token type 集（`)`/`]`/`}`）：从 token.toml 的 bracket pairs
        # 配置推导（bracket_type_map），不硬编码具体 type。行尾闭合括号表示
        # 括号组（端口列表/参数列表/表达式）在本行闭合——语句若继续（`);` /
        # `) csr (`），下一行不再是无界续行，避免 `);` 被当成语句头续行
        self.close_bracket_types = {
            self.lexer.bracket_type_map[c] for c in self.lexer.close_brackets
        }

    def scan(self, source: str) -> list[LineContext]:
        tokens = self.lexer.tokenize(source)
        return self._scan_tokens(tokens)

    def _scan_tokens(self, tokens: list) -> list[LineContext]:
        """单次 token 遍历 → 每行 LineContext（状态见 `_ScanState`，分派见三个 handler）。"""
        state = _ScanState(
            contexts=[],
            scope_path=[ScopeNode(ScopeKind.ROOT)],
            ifdef_branches=[],
        )
        tokens = list(tokens)
        for _ti in range(len(tokens)):
            t = tokens[_ti]
            if t.type in self._TRIVIA:
                if t.type == "comment":
                    self._handle_comment(t, state)
                elif t.type == "newline":
                    self._handle_newline(state)
                # skip space.* tokens
                continue
            self._handle_content_token(t, _ti, tokens, state)
        if state.line_buf:
            self._emit_line(
                state.contexts,
                state.line_buf,
                state.line_num,
                state.scope_path,
                state.ifdef_branches,
                state.pending_block_header,
                state.pending_block_footer,
                state.line_has_comment,
                state.pending_case_item,
                state.pending_stmt_header,
                state.pending_is_else,
                state.multi_active,
                state.multi_header_line if state.multi_active else 0,
            )
        return state.contexts

    def _handle_comment(self, t, state: "_ScanState") -> None:
        """注释 token：多行块注释按物理行拆分逐行产 context；单行只记标记。"""
        if "\n" in t.content:
            # 多行块注释（`/* ... */` 跨多行）：按物理行拆分逐行产出
            # context，保持与源行对齐（否则 ctxs 数 < 源行数，后续所有
            # 行 line_number/缩进错位）
            segs = t.content.split("\n")
            state.line_buf.append(segs[0])
            state.pending_line_comment = True
            for seg_idx, seg in enumerate(segs[1:]):
                self._emit_line(
                    state.contexts,
                    state.line_buf,
                    state.line_num,
                    state.scope_path,
                    state.ifdef_branches,
                    state.pending_block_header,
                    state.pending_block_footer,
                    True,
                    state.pending_case_item,
                    False,
                    False,
                    False,
                    0,
                    False,
                    False,
                    False,
                    seg_idx > 0,  # 首迭代产的是注释首行（不算内部段）
                )
                state.line_buf = [seg]
                state.line_num += 1
            # 末段（含块注释闭合标记）留在 line_buf，由换行处产行：
            # 继承 is_comment_cont（缩进随注释首行平移，保留 ` */` 对齐）
            state.pending_comment_cont = True
        else:
            state.line_has_comment = True
            if not state.line_buf:  # 行首是注释 → 纯注释行
                state.pending_line_comment = True
            state.line_buf.append(t.content)

    def _handle_newline(self, state: "_ScanState") -> None:
        """换行 token：算本行标志 → 产出 context → 更新下行续行状态 → 重置行状态。"""
        # 模块端口列表结束行（`);`）→ 对齐模块头（0 级）；
        # 先判断再重置 in_port_list
        port_list_end = (
            state.in_port_list and state.last_line_nontrivia in self.stmt_end_tokens
        )
        # if/for 单行体（body 同行，如 `if (X) stmt;`）：行尾分号
        # 表示语句头已在同行结束 → 非单语句头；同时结束端口列表
        if state.last_line_nontrivia in self.stmt_end_tokens:
            state.pending_stmt_header = False
            state.in_port_list = False
        # 多行语句续行：本行是否续行（行首运算符判定见 `_line_start_op_cont`，
        # 行尾运算符判定见 `_line_end_op_cont`）
        start_op = self._line_start_op_cont(state, state.multi_active)
        is_cont = state.multi_active or start_op
        op_cont = start_op or self._line_end_op_cont(state)
        hdr_line = state.multi_header_line if is_cont else 0
        hdr_extra = state.multi_depth_extra if is_cont else 0
        line_ends_stmt = state.last_line_nontrivia in self.stmt_end_tokens
        is_block_line = (
            state.pending_block_header is not None
            or state.pending_block_footer is not None
            or (state.line_first_token in self.openers)
            or (state.line_first_token in self.closers)
        )
        is_directive = self._is_directive_line(state.line_buf)
        is_pure_comment = self._is_pure_comment_line(
            state.pending_line_comment, state.line_buf
        )
        is_decl = self._is_decl_line(state)
        decl_op_cont = self._decl_op_cont(state, is_decl)

        # 更新下一行续行状态（续行链判定与注释行例外见 `_update_next_line_state`）
        self._update_next_line_state(
            state,
            is_cont=is_cont,
            op_cont=op_cont,
            line_ends_stmt=line_ends_stmt,
            is_block_line=is_block_line,
            is_directive=is_directive,
            is_decl=is_decl,
            decl_op_cont=decl_op_cont,
            is_pure_comment=is_pure_comment,
        )
        self._emit_line(
            state.contexts,
            state.line_buf,
            state.line_num,
            state.scope_path,
            state.ifdef_branches,
            state.pending_block_header,
            state.pending_block_footer,
            state.line_has_comment,
            state.pending_case_item,
            state.pending_stmt_header,
            state.pending_is_else,
            is_cont,
            hdr_line,
            port_list_end,
            bool(hdr_extra),
            is_directive,
            state.pending_comment_cont,
        )
        self._reset_line_state(state)

    # ── 行标志判定（`_handle_newline` 的分步）──

    def _line_start_op_cont(self, state: "_ScanState", is_cont: bool) -> bool:
        """行首是运算符 → 表达式续行（`&&`/`||`/`*`/`+`/`?`/`:` 等，不含 `.`）。

        折行 pass 拆出的续行行尾有分号，但仍属上一语句的表达式部分；二次 format
        时靠行首运算符识别续行，缩进相对语句头 +1。`.` 是实例端口连接行，不属
        运算符续行；`$`（symbol.base.dollar）是系统任务前缀（`$display` 等），
        不是运算符——否则 if 单语句体的多行 $display 被误判续行。
        """
        first = state.line_first_token
        return (
            not is_cont
            and first is not None
            and first.startswith(SYMBOL_PREFIX)
            and not first.endswith(".dot")
            and not first.endswith(".dollar")
        )

    def _line_end_op_cont(self, state: "_ScanState") -> bool:
        """行尾是运算符（`&&`/`+`/`:` 等留在行尾，续行从操作数开始）→ 置 op_cont。

        只供下一行判断，**不**作为 hdr 指向 line_num-1：行尾运算符的行若是续行
        （多折续行，如 `cond) && ENABLE_COUNTERS &&` 行尾 && 的下一行），其深度
        已含续行偏移，再相对 +1 会多一级（once 20 vs twice 16 漂移）。续行一律
        对齐语句头 multi_header_line。comma 是分隔符不是运算符（多行声明/端口
        列表的续行应对齐语句头 multi_header_line，否则 `reg a,\n b,\n c;` 续行
        hdr 逐行指向上一行，缩进递增）。
        """
        last = state.last_line_nontrivia
        return (
            last is not None
            and last.startswith(SYMBOL_PREFIX)
            and not last.endswith(".dot")
            and not last.endswith(".comma")
            and last not in self.stmt_end_tokens
        )

    def _is_directive_line(self, line_buf: list[str]) -> bool:
        """指令行：反引号开头且行内无 `(`。

        纯指令（`define/`include/`ifdef 等）无括号；宏调用语句（`LUI: $display(...)`
        或 `debug(...)`）含 `(`，是语句形态非指令，wrap 可折其参数。
        """
        return (
            bool(line_buf)
            and line_buf[0].lstrip().startswith("`")
            and "(" not in "".join(line_buf)
        )

    def _is_pure_comment_line(self, pending_line_comment: bool, line_buf: list[str]) -> bool:
        """纯注释行（已标记行注释，或行首是 `//`/`/*`/`*/`）。"""
        return pending_line_comment or (
            bool(line_buf)
            and (
                line_buf[0].lstrip().startswith("//")
                or line_buf[0].lstrip().startswith("/*")
                or line_buf[0].lstrip().startswith("*/")
            )
        )

    def _is_decl_line(self, state: "_ScanState") -> bool:
        """声明行（行首 token 在 decl_headers）。"""
        return (
            state.line_first_token is not None
            and state.line_first_token in self.decl_headers
        )

    def _decl_op_cont(self, state: "_ScanState", is_decl: bool) -> bool:
        """声明行行尾是运算符（`wire a = x &&` 的 `&&`，wrap 折行断点）。

        → 声明带初始化表达式且被折行，仍属续行（is_decl 不阻断）。
        """
        last = state.last_line_nontrivia
        return (
            is_decl
            and last is not None
            and last.startswith(SYMBOL_PREFIX)
            and not last.endswith(".dot")
            and last not in self.stmt_end_tokens
        )

    def _ends_continuation_chain(
        self,
        state: "_ScanState",
        *,
        op_cont: bool,
        line_ends_stmt: bool,
        is_block_line: bool,
        is_directive: bool,
        is_decl: bool,
        decl_op_cont: bool,
    ) -> bool:
        """本行是否结束续行链：语句结束 / 块头尾 / 单语句头 / 指令 / 端口列表 /
        case 分支项 / 声明行 / 空行 / 行尾闭合括号 → 非续行。

        - 行尾运算符（`if (A &&` 的 `&&`，wrap 块头折行断点）→ 表达式未结束，
          强制下行续行——否则 pending_stmt_header（if 是控制流头）把
          multi_active 置 False，块头折行的续行（`B) begin`）缩进按 scope_depth
          算，二次 format 漂移（wrap 折行给 hdr+4，boundary 未识别给 scope_depth）。
        - 行尾闭合括号（`)`/`]`/`}`）：括号组本行闭合，续行链到此为止——否则
          `.b(b)` 后的 `);` 会被当成续行（+1 级），实例端口列表结束行缩进错位。
        """
        return not op_cont and (
            line_ends_stmt
            or is_block_line
            or state.pending_stmt_header
            or is_directive
            or state.in_port_list
            or state.pending_case_item
            or (is_decl and not decl_op_cont)
            or not state.line_buf
            or state.last_line_nontrivia in self.close_bracket_types
        )

    def _update_next_line_state(
        self,
        state: "_ScanState",
        *,
        is_cont: bool,
        op_cont: bool,
        line_ends_stmt: bool,
        is_block_line: bool,
        is_directive: bool,
        is_decl: bool,
        decl_op_cont: bool,
        is_pure_comment: bool,
    ) -> None:
        """更新下一行的续行状态（multi_active / multi_header_line / multi_depth_extra）。

        注释行不打断续行：纯注释（`// State` 等）是行内说明，实例化端口列表/多行
        表达式还在继续——注释行自身保持上一行 multi_active（不置 False），后续
        端口行仍识别为续行。否则 `serv_csr ... (\n .i_cnt7, // RS1 read port` 的
        注释后端口行顶格，缩进丢失。

        续行链结束时重置语句头行号——否则后续被误判为续行的行（如 if 单语句体的
        多行 $display）会继承旧语句头（hdr 错位，二次 format 漂移）。
        """
        if is_pure_comment:
            return  # 保持 multi_active（不打断续行链）
        if self._ends_continuation_chain(
            state,
            op_cont=op_cont,
            line_ends_stmt=line_ends_stmt,
            is_block_line=is_block_line,
            is_directive=is_directive,
            is_decl=is_decl,
            decl_op_cont=decl_op_cont,
        ):
            state.multi_active = False
            state.multi_header_line = 0
            state.multi_depth_extra = 0
            return
        state.multi_active = True
        # 只有新语句头才记下 header 行号；续行保持语句头（同级）。语句头行尾
        # 是 `=`（连续赋值，三目链 `? :` 续行 ref 用 +2）。
        if not is_cont:
            state.multi_header_line = state.line_num
            state.multi_depth_extra = (
                1 if state.last_line_nontrivia == "symbol.base.equal" else 0
            )

    def _reset_line_state(self, state: "_ScanState") -> None:
        """行产出后重置累加量（供下一行使用）。"""
        state.line_buf = []
        state.line_num += 1
        state.line_has_comment = False
        state.pending_block_header = None
        state.pending_block_footer = None
        state.pending_case_item = False
        state.pending_stmt_header = False
        state.pending_is_else = False
        state.pending_line_comment = False
        state.pending_comment_cont = False
        state.line_first_token = None
        state.last_line_nontrivia = None

    def _handle_content_token(self, t, _ti: int, tokens: list, state: "_ScanState") -> None:
        """非 trivia token：先入行缓冲，再按 token 类型分派（ifdef/花括号/块开闭/语句头/case 项）。"""
        state.line_buf.append(t.content)
        state.last_line_nontrivia = t.type
        if state.line_first_token is None:
            state.line_first_token = t.type

        # 行首 token 是 else → else 链行（自身不悬挂，与 if/end 对齐；
        # 其单语句体仍由 sst 触发下一行悬挂）
        if t.type == "keyword.else" and not state.line_buf[:-1]:
            state.pending_is_else = True

        if t.type in self.ifdef_set:
            self._handle_ifdef_token(t, state.scope_path, state.ifdef_branches)
        elif t.type == "bracket.l_curly_bracket":
            self._handle_curly_open(t, _ti, tokens, state)
        elif t.type == "bracket.r_curly_bracket":
            self._handle_curly_close(t, state)
        elif t.type in self.openers:
            self._handle_opener_token(t, state)
        elif t.type in self.closers:
            self._handle_closer_token(t, state)

        self._track_stmt_header_and_case_item(t, state)

    def _handle_curly_open(self, t, _ti: int, tokens: list, state: "_ScanState") -> None:
        """`{`：天然块边界；表达式花括号（concat/replicate）计数排除、不入块栈。

        `{` 同行后还有内容（`_same_line_next`）→ 表达式花括号；否则是块
        （TypeBody/TypeImplDecl 等结构块）。括号深度通用处理，不硬编码结构名。
        """
        if _same_line_next(tokens, _ti, self._TRIVIA):
            state.brace_expr_depth += 1
        else:
            state.pending_block_header = ScopeKind.BLOCK
            self._handle_opener(
                t, ScopeKind.BLOCK, state.scope_path, state.ifdef_branches
            )

    def _handle_curly_close(self, t, state: "_ScanState") -> None:
        """`}`：优先闭合表达式花括号（计数 -1），否则 pop 块栈。"""
        if state.brace_expr_depth > 0:
            state.brace_expr_depth -= 1  # 闭合表达式 `}`，不动块栈
        else:
            state.pending_block_footer = ScopeKind.BLOCK
            self._handle_closer(t, state.scope_path, state.ifdef_branches)

    def _handle_opener_token(self, t, state: "_ScanState") -> None:
        """块入口 token：记 kind、端口列表/case 深度/generate 特殊处理，再入块栈。"""
        kind = self._scope_kind_for(t.type)
        if kind == ScopeKind.MODULE:
            state.in_port_list = True
        if kind == ScopeKind.CASE:
            state.case_depth = self._current_depth(state.scope_path) + 1
        # generate/endgenerate 不贡献缩进层级：匹配单行 `generate if ... begin`
        # 风格（generate 块内容与 module 内容同级），其指令行按普通行缩进
        if kind != ScopeKind.GENERATE:
            state.pending_block_header = kind
        # 行内有 begin 块（如 `if (X) begin`）→ 非单语句体，取消悬挂
        if kind == ScopeKind.BLOCK:
            state.pending_stmt_header = False
        self._handle_opener(t, kind, state.scope_path, state.ifdef_branches)

    def _handle_closer_token(self, t, state: "_ScanState") -> None:
        """块终结 token：记 kind、case 深度复位，再出栈。"""
        kind = self._scope_kind_for_closer(t.type)
        if kind != ScopeKind.GENERATE:
            state.pending_block_footer = kind
        self._handle_closer(t, state.scope_path, state.ifdef_branches)
        if kind == ScopeKind.CASE:
            state.case_depth = -1

    def _track_stmt_header_and_case_item(self, t, state: "_ScanState") -> None:
        """语句头候选与 case 分支项标记（每 token 一次，与 token 类型分支无关）。"""
        # 控制流语句头（if/for/else 等，从规则推导）→ 本行是单语句头候选
        if t.type in self.stmt_headers:
            state.pending_stmt_header = True
        if self._is_case_item_token(t, state):
            state.pending_case_item = True

    def _is_case_item_token(self, t, state: "_ScanState") -> bool:
        """case 分支项 token：在 case 层深上遇到关键字（含 default）。

        排除控制流语句头（if/for/while 等，stmt_headers）——它们也是
        KEYWORD_PREFIX，但 case 分支项是 `3'b100:`/`default:` 值+冒号形态，
        不是语句。否则 case 分支内的 `if (A &&` 被误标 case_item，
        indent 按 case_item_hang（depth+1）缩进，二次 format 漂移。
        """
        if state.case_depth < 0:
            return False
        if self._current_depth(state.scope_path) != state.case_depth + 1:
            return False
        if t.type in self.stmt_headers:
            return False
        return t.type.startswith(KEYWORD_PREFIX) or t.type == "keyword.default"

    def _scope_kind_for(self, token_type: str) -> ScopeKind:
        return self.scope_kind_map.get(token_type, ScopeKind.BLOCK)

    def _scope_kind_for_closer(self, token_type: str) -> ScopeKind | None:
        return self.scope_kind_map.get(token_type)

    def _current_depth(self, scope_path: list) -> int:
        return len(scope_path) - 1

    def _snapshot_scope(self, scope_path: list[ScopeNode]) -> list[ScopeNode]:
        return list(scope_path[1:])

    def _restore_scope(
        self, scope_path: list[ScopeNode], snapshot: list[ScopeNode]
    ) -> None:
        scope_path[:] = [scope_path[0]] + list(snapshot)

    def _handle_ifdef_token(self, t, scope_path, ifdef_branches):
        if t.type in ("macro.ifdef", "macro.ifndef"):
            branch = ScopeBranch(
                condition=t.content, openers=self._snapshot_scope(scope_path)
            )
            ifdef_branches.append(branch)
        elif t.type in ("macro.else", "macro.elsif"):
            if ifdef_branches:
                branch = ifdef_branches[-1]
                self._restore_scope(scope_path, branch.openers)
                ifdef_branches[-1] = ScopeBranch(
                    condition=t.content, openers=branch.openers
                )
        elif t.type == "macro.endif":
            if ifdef_branches:
                branch = ifdef_branches.pop()
                self._restore_scope(scope_path, branch.openers)

    def _handle_opener(self, t, kind, scope_path, ifdef_branches):
        if kind == ScopeKind.GENERATE:
            return  # generate 不贡献缩进层级（不入栈）
        node = ScopeNode(kind=kind, name=t.content, token_line=t.line)
        scope_path.append(node)
        if ifdef_branches:
            ifdef_branches[-1].extra_openers.append(node)

    def _handle_closer(self, t, scope_path, ifdef_branches):
        del ifdef_branches  # 内部方法参数，本分支不消费
        if self._scope_kind_for_closer(t.type) == ScopeKind.GENERATE:
            return  # endgenerate 不弹栈（generate 未入栈）
        if len(scope_path) > 1:
            scope_path.pop()

    def _emit_line(
        self,
        contexts,
        buf,
        line_num,
        scope_path,
        ifdef_branches,
        block_header_of,
        block_footer_of,
        has_comment,
        is_case_item,
        single_stmt_header=False,
        is_else_header=False,
        multi_cont=False,
        multi_hdr_line=0,
        port_list_end=False,
        multi_extra=False,
        is_directive=False,
        is_comment_cont=False,
    ):
        if not buf:
            contexts.append(LineContext(line_number=line_num, text=""))
            return
        line = "".join(buf)
        kinds = [s.kind for s in scope_path]
        ctx = LineContext(
            line_number=line_num,
            text=line,
            scope_path=kinds,
            scope_depth=self._current_depth(scope_path),
            in_ifdef=bool(ifdef_branches),
            ifdef_condition=ifdef_branches[-1].condition if ifdef_branches else "",
            scope_kind_stack=list(kinds[1:]),  # 不含 ROOT
            block_header_of=block_header_of,
            block_footer_of=block_footer_of,
            has_trailing_comment=has_comment,
            is_case_item=is_case_item,
            single_stmt_header=single_stmt_header,
            is_else_header=is_else_header,
            multi_line_cont=multi_cont,
            multi_header_line=multi_hdr_line,
            port_list_end=port_list_end,
            multi_extra=multi_extra,
            is_directive=is_directive,
            is_comment_cont=is_comment_cont,
        )
        contexts.append(ctx)
