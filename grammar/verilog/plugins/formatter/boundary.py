"""boundary.py — 结构边界扫描器

对 token 流做单次遍历，追踪结构边界（module/begin/end/ifdef/else/endif/case 等），
为每条行产出其在 scope 栈中的上下文位置。

核心能力：
  - 块起止符追踪（begin/end, module/endmodule, generate/endgenerate, case/endcase 等）
  - 从语法规则自动推导 token → ScopeKind 映射
  - ifdef/else/endif 分支感知（分支内独立追踪，endif 处收敛校验）
  - 行级别 scope 快照 + 块头/块尾标记 + 行内注释标记
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from lexer import Lexer


# ── BlockTokenMap ──

@dataclass
class BlockTokenMap:
    """由语法规则构建的块边界映射。"""
    openers: set[str] = field(default_factory=set)
    closers: set[str] = field(default_factory=set)
    ifdef_set: set[str] = field(default_factory=set)
    scope_kind_map: dict[str, "ScopeKind"] = field(default_factory=dict)


def _resolve_first_tokens(tree: dict, feat: dict | None, visited: set[str] | None = None) -> set[str]:
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


def _infer_scope_kind(rule_name: str, first_tokens: set[str]) -> "ScopeKind":
    """从规则名或起始 token 推断 ScopeKind。"""
    # 按规则名匹配
    name_map = {
        "ModuleBlock": ScopeKind.MODULE,
        "BeginEnd": ScopeKind.BLOCK,

        "FuncDeclANSI": ScopeKind.FUNCTION,
        "FuncDeclOld": ScopeKind.FUNCTION,
        "TaskDeclANSI": ScopeKind.TASK,
        "TaskDeclOld": ScopeKind.TASK,
        "GenerateBlock": ScopeKind.GENERATE,
        "LoopGen": ScopeKind.GENERATE,
        "CaseStatement": ScopeKind.CASE,
    }
    if rule_name in name_map:
        return name_map[rule_name]
    # 按 token 类型回退
    token_map = {
        "keyword.module": ScopeKind.MODULE,
        "keyword.begin": ScopeKind.BLOCK,
        "keyword.function": ScopeKind.FUNCTION,
        "keyword.task": ScopeKind.TASK,
        "keyword.generate": ScopeKind.GENERATE,
        "keyword.case": ScopeKind.CASE,
        "keyword.casex": ScopeKind.CASE,
        "keyword.casez": ScopeKind.CASE,
        "keyword.always": ScopeKind.ALWAYS,
        "keyword.initial": ScopeKind.INITIAL,
        "keyword.for": ScopeKind.FOR_LOOP,
        "keyword.forever": ScopeKind.FOR_LOOP,
        "keyword.repeat": ScopeKind.FOR_LOOP,
        "keyword.while": ScopeKind.FOR_LOOP,
    }
    for tok in first_tokens:
        if tok in token_map:
            return token_map[tok]
    return ScopeKind.BLOCK


# ── 边界 token 集合（由语法规则自动构建）──

def build_block_tokens(rules: dict) -> BlockTokenMap:
    """从语法规则构建边界 token 集合。

    自动推导：
      - is_block = True 的规则 → 开/闭 token 直接收集
      - 有 end_case 关键字终结符的规则（如 case/endcase）→ 作为隐式 scope
      - call 链递归解析（如 @CaseKeyword → keyword.case|casex|casez）
      - 每个 opener token 自动关联 ScopeKind

    Returns:
        BlockTokenMap 包含 openers / closers / ifdef_set / scope_kind_map
    """
    from linter.grammar_slicer import build_slice_tree, get_start_tokens

    tree = build_slice_tree(rules)
    openers: set[str] = set()
    closers: set[str] = set()
    scope_kind_map: dict[str, ScopeKind] = {}

    # ── 第一轮：is_block = True 的规则 ──
    anon_blocks: set[str] = set()
    for name, info in tree.items():
        if not info.get("is_block"):
            continue
        closers |= info.get("end_case", set())
        prods = info.get("prods", [])
        if not prods:
            anon_blocks.add(name)
        else:
            tokens = get_start_tokens(prods)
            openers |= tokens

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
                tokens = get_start_tokens(prods)
                openers |= tokens
                for f in reversed(prods):
                    if f.get("type") == "token":
                        closers.add(f["token_type"])
                        break
                seen_parents.add(name)
                break

    # ── 第二轮：有 end_case 关键字终结符的隐式块（case/function/task 等）──
    _END_KEYWORD_MARKERS = frozenset({
        "keyword.endcase", "keyword.endfunction", "keyword.endtask",
        "keyword.endgenerate", "keyword.endmodule",
    })
    for name, info in tree.items():
        if info.get("is_block"):
            continue  # 第一轮已处理
        ec = info.get("end_case", set())
        # 只关注有明确关键字终结符的规则
        if not ec or not ec & _END_KEYWORD_MARKERS:
            continue
        prods = info.get("prods", [])
        if not prods:
            continue
        # 递归解析起始 token
        tokens = _resolve_first_tokens(tree, prods[0])
        if tokens:
            openers |= tokens
            closers |= ec & _END_KEYWORD_MARKERS  # 只取关键字终结符

    # ── 构建 scope_kind_map ──
    for name, info in tree.items():
        is_block = info.get("is_block", False)
        ec = info.get("end_case", set())
        if not is_block and not (ec & _END_KEYWORD_MARKERS):
            continue
        prods = info.get("prods", [])
        if not prods:
            continue
        tokens = _resolve_first_tokens(tree, prods[0])
        if not tokens:
            tokens = get_start_tokens(prods)
        for tok in tokens:
            if tok not in scope_kind_map:
                scope_kind_map[tok] = _infer_scope_kind(name, tokens)

    ifdef_set = {"macro.ifdef", "macro.ifndef", "macro.else", "macro.elsif", "macro.endif"}
    return BlockTokenMap(
        openers=openers,
        closers=closers,
        ifdef_set=ifdef_set,
        scope_kind_map=scope_kind_map,
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


# ── 边界扫描器 ──

class BoundaryScanner:
    """单次 token 流遍历 → 为每行产出 LineContext。

   ifdef/else/endif 分支各自维护独立的 scope 栈：
     1. 进入 ifdef 时快照当前 scope_path → branch.openers
     2. 分支内 opener 记入 branch.extra_openers
     3. 每个分支结束后（else/elsif/endif），scope_path 恢复为快照
     4. endif 处校验所有分支的栈收敛到同一深度
    """

    _TRIVIA = frozenset({"newline", "space.indent", "space.dedent", "space.fold", "comment"})
    _COMMENT_LINE = frozenset({"comment"})

    def __init__(self, rules: dict, lexer: Lexer):
        self.token_map = build_block_tokens(rules)
        self.openers = self.token_map.openers
        self.closers = self.token_map.closers
        self.ifdef_set = self.token_map.ifdef_set
        self.scope_kind_map = self.token_map.scope_kind_map
        self.lexer = lexer

    def scan(self, source: str) -> list[LineContext]:
        tokens = self.lexer.tokenize(source)
        return self._scan_tokens(tokens)

    def _scan_tokens(self, tokens: list) -> list[LineContext]:
        contexts: list[LineContext] = []
        scope_path: list[ScopeNode] = [ScopeNode(ScopeKind.ROOT)]
        ifdef_branches: list[ScopeBranch] = []
        line_buf: list[str] = []
        line_num = 1
        line_has_comment = False
        pending_block_header: ScopeKind | None = None
        pending_block_footer: ScopeKind | None = None
        pending_case_item = False
        # 追踪最近的 case 深度，用于识别 case 分支项
        case_depth = -1

        for t in tokens:
            if t.type in self._TRIVIA:
                if t.type == "comment":
                    line_has_comment = True
                    line_buf.append(t.content)
                elif t.type == "newline":
                    self._emit_line(
                        contexts, line_buf, line_num, scope_path,
                        ifdef_branches, pending_block_header,
                        pending_block_footer, line_has_comment, pending_case_item,
                    )
                    line_buf = []
                    line_num += 1
                    line_has_comment = False
                    pending_block_header = None
                    pending_block_footer = None
                    pending_case_item = False
                # skip space.* tokens
                continue

            line_buf.append(t.content)

            if t.type in self.ifdef_set:
                self._handle_ifdef_token(t, scope_path, ifdef_branches)
            elif t.type in self.openers:
                kind = self._scope_kind_for(t.type)
                if kind == ScopeKind.CASE:
                    case_depth = self._current_depth(scope_path) + 1
                pending_block_header = kind
                self._handle_opener(t, kind, scope_path, ifdef_branches)
            elif t.type in self.closers:
                kind = self._scope_kind_for_closer(t.type)
                pending_block_footer = kind
                self._handle_closer(t, scope_path, ifdef_branches)
                if kind == ScopeKind.CASE:
                    case_depth = -1

            # 识别 case 分支项：在 case 深度上遇到标识符或 default
            if case_depth >= 0 and self._current_depth(scope_path) == case_depth + 1:
                if t.type.startswith("keyword.") or t.type == "keyword.default":
                    pending_case_item = True

        if line_buf:
            self._emit_line(
                contexts, line_buf, line_num, scope_path,
                ifdef_branches, pending_block_header,
                pending_block_footer, line_has_comment, pending_case_item,
            )

        return contexts

    def _scope_kind_for(self, token_type: str) -> ScopeKind:
        return self.scope_kind_map.get(token_type, ScopeKind.BLOCK)

    def _scope_kind_for_closer(self, token_type: str) -> ScopeKind | None:
        m = {
            "keyword.endmodule": ScopeKind.MODULE,
            "keyword.endfunction": ScopeKind.FUNCTION,
            "keyword.endtask": ScopeKind.TASK,
            "keyword.endgenerate": ScopeKind.GENERATE,
            "keyword.endcase": ScopeKind.CASE,
            "keyword.end": ScopeKind.BLOCK,
        }
        return m.get(token_type)

    def _current_depth(self, scope_path: list) -> int:
        return len(scope_path) - 1

    def _snapshot_scope(self, scope_path: list[ScopeNode]) -> list[ScopeNode]:
        return list(scope_path[1:])

    def _restore_scope(self, scope_path: list[ScopeNode], snapshot: list[ScopeNode]) -> None:
        scope_path[:] = [scope_path[0]] + list(snapshot)

    def _handle_ifdef_token(self, t, scope_path, ifdef_branches):
        if t.type in ("macro.ifdef", "macro.ifndef"):
            branch = ScopeBranch(condition=t.content, openers=self._snapshot_scope(scope_path))
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
        node = ScopeNode(kind=kind, name=t.content, token_line=t.line)
        scope_path.append(node)
        if ifdef_branches:
            ifdef_branches[-1].extra_openers.append(node)

    def _handle_closer(self, t, scope_path, ifdef_branches):
        if len(scope_path) > 1:
            scope_path.pop()

    def _emit_line(self, contexts, buf, line_num, scope_path, ifdef_branches,
                   block_header_of, block_footer_of, has_comment, is_case_item):
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
        )
        contexts.append(ctx)

