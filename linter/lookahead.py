"""lookahead.py — 动态前瞻消歧表。

从规则树（build_slice_tree 产物）预计算，供发现阶段（discovery）使用：

Doc: linter/linter_architecture.md

    1. keyword_map  — 具体 token 类型 → 规则名列表（A 类：关键字/具体符号触发）
    2. ident_candidates — 标识符触发的规则（B 类），每条含判别前缀路径集，
       单一全局集合（不按上下文分组——所有块内上下文共享同一组候选，靠
       Level 1 前瞻/Level 2 试解析精确筛选）

B 类消歧 = 动态两级（变长前瞻 + 试解析兜底）：
    - Level 1（变长前瞻）：首 token 相同时逐 token 预视，每预视一个就缩小
      候选路径集，直到只剩唯一一条（前瞻深度到语句边界块为止，不穿透）。
    - Level 2（试解析）：候选生成式含深层 call / 前缀无法静态表达 / 边界内
      未收敛时，对每个候选用完整 production 试解析匹配（复用 RuleMatcher），
      比较匹配结果（错误数 + 消费位置）定夺。
    例如 `foo`：
        foo = ...   → BlockingAssign（前缀 ["="]）
        foo <= ...  → NonBlockingAssign（前缀 ["<="]）
        foo(...)    → SubroutineCall（前缀 ["("]）
        foo u1(...) → ModuleInst（前缀 [id, "("]，需预视 2 token）
"""

from __future__ import annotations

import os
import sys

from core.define import Token

from core.utils import square_bracket_types
from core.token_protocol import TRIVIA_TOKEN_TYPES, split_token_types

# trivia token 集合（引擎 token 协议，单一事实源 core/token_protocol.py）
_TRIVIA = TRIVIA_TOKEN_TYPES
from .grammar_slicer import _collect_first_start_tokens

# 消歧决策 trace 开关（环境变量兜底，命令行/测试可传 trace=True 显式开启）：
# 输出 Level 1（seen 序列/候选淘汰/分支决策）与 Level 2（各候选试解析的
# errs/consumed、best 选择）到 stderr——classify 返回非预期结果时定位
# "为什么"，与 parser 的 set_trace 同风格。默认关闭，零行为影响。
_TRACE_ENV = os.environ.get("TPC_LINT_TRACE", "").strip() not in ("", "0")

# 方括号开/闭类型（从 lexer.bracket_map 推导，构造期配置已加载）。
# 模块级惰性缓存：_feat_token_paths 等模块级函数与实例方法共用。
_SQUARE_LR: tuple[str, str] | None = None


def _square_bracket_lr() -> tuple[str, str]:
    global _SQUARE_LR
    if _SQUARE_LR is None:
        _SQUARE_LR = square_bracket_types()
    return _SQUARE_LR


def _first_of(feat: dict | None, tree: dict) -> set[str]:
    """单个 feature 的起始 token 集。"""
    if feat is None:
        return set()
    return _collect_first_start_tokens(feat, tree)


def _rule_first(name: str, tree: dict) -> set[str]:
    info = tree.get(name)
    if not info or not info.get("prods"):
        return set()
    return _first_of(info["prods"][0], tree)




# 表达式黑盒：带 pratt 标识的规则（Expression/运算符链）由 pratt 解析器专门处理，
# first 是 id（与触发相同）或内部复杂，前缀无判别价值。作为"终止元素"：
# 路径在此结束，不继续展开其后的 token。按 pratt 标识识别而非硬编码规则名
# （换一套语法配置，表达式规则即使改名也带 pratt=true）。
# 前缀路径最大长度（防御；真实判别前缀都很短，到边界块即止）
_MAX_PREFIX_LEN = 8


def _feat_token_paths(feat: dict | None, tree: dict) -> set[tuple[str, ...]] | None:
    """单个 production 元素的判别 token 序列集（按 feature 类型分派）。

    返回 set[tuple[str, ...]]：该元素可能的前缀 token 序列（含空元组 = epsilon）。
    返回 None：该元素是**终止元素**（表达式黑盒/语句/块边界）——路径在此结束，
    不继续展开其后的 token。前缀在此截断，后续由变长前瞻在边界块内区分。

    各类型语义见 `_paths_choice` / `_paths_seq` / `_paths_optional` /
    `_paths_repeat` / `_paths_call`。
    """
    if feat is None:
        return {()}
    typ = feat.get("type")
    if typ == "token":
        return {(feat["token_type"],)}
    if typ == "choice":
        return _paths_choice(feat, tree)
    if typ == "seq":
        return _paths_seq(feat, tree)
    if typ == "optional":
        return _paths_optional(feat, tree)
    if typ in ("repeat", "plus"):
        return _paths_repeat(feat, tree)
    if typ == "call":
        return _paths_call(feat, tree)
    return {()}


def _paths_choice(feat: dict, tree: dict) -> set[tuple[str, ...]] | None:
    """`choice`：各分支路径并集；**任一分支终止 → 整体终止**（None）。"""
    result: set[tuple[str, ...]] = set()
    for alt in feat.get("alternatives", []):
        sub = _feat_token_paths(alt, tree)
        if sub is None:
            return None
        result |= sub
    return result


def _paths_seq(feat: dict, tree: dict) -> set[tuple[str, ...]] | None:
    """`seq`：逐元素做笛卡尔拼接；遇终止元素 → 保留到该元素为止的前缀。"""
    result: set[tuple[str, ...]] = {()}
    for item in feat.get("items", []):
        sub = _feat_token_paths(item, tree)
        if sub is None:
            return result
        result = {p + s for p in result for s in sub}
    return result


def _paths_repeat(feat: dict, tree: dict) -> set[tuple[str, ...]] | None:
    """`repeat` / `plus`：0 次 或 1 次（再长不增加判别深度，到边界块为止）。"""
    sub = _feat_token_paths(feat.get("elem"), tree)
    if sub is None:
        return None
    return {()} | sub


def _paths_optional(feat: dict, tree: dict) -> set[tuple[str, ...]] | None:
    """`optional`：epsilon + 子路径；子路径终止时查复杂 call 的括号特例。"""
    elem = feat.get("elem")
    sub = _feat_token_paths(elem, tree)
    if sub is None:
        sub = _optional_bracket_paths(elem, tree)
        if sub is None:
            return None  # 可选复杂 call → 截断（内容不可静态判别）
    return {()} | sub


def _optional_bracket_paths(elem: dict | None, tree: dict) -> set[tuple[str, ...]] | None:
    """可选**复杂 call** 的括号特例：仅当 first 含 `[` 时保留 epsilon + first 集。

    `[` 可被 Level 1 括号配对跳过（如 `@Range?` 的 `[7:0]`）——否则
    `function [7:0]` 的 `[` 不在判别路径（A 类多候选消歧被淘汰）而漏检。
    其他复杂 call（如 `@ParamOverride?` 的 `#(...)`，Level 1 无法跳过其内部）
    维持截断 → paths 空走 Level 2 试解析，避免 `#` 后的 `(` 逐 token 误淘汰。
    """
    if elem is None or elem.get("type") != "call":
        return None
    info = tree.get(elem.get("name", "")) or {}
    prods = info.get("prods") or []
    if not prods:
        return None
    firsts = {t for t in _collect_first_start_tokens(prods[0], tree)}
    if _square_bracket_lr()[0] not in firsts:
        return None
    return {()} | {(t,) for t in firsts}


def _paths_call(feat: dict, tree: dict) -> set[tuple[str, ...]] | None:
    """`call`：pratt 表达式黑盒 / 语句块边界 / 非原子复杂调用 → 终止（None）。

    只对**原子**规则（`is_atom`）展开其 production 首元素集：参数列表、端口连接
    这类非原子结构内容不可静态判别，截断后由 Level 2 试解析兜底。
    """
    info = tree.get(feat.get("name", ""))
    if info is None:
        return None
    if info.get("pratt") or info.get("is_statement") or info.get("is_block"):
        return None
    if not info.get("is_atom"):
        return None
    prods = info.get("prods", [])
    if not prods:
        return None
    return {(t,) for t in _collect_first_start_tokens(prods[0], tree)}


def _build_prefix_paths(prods: list[dict], tree: dict) -> set[tuple[str, ...]]:
    """从 production（id 之后的元素）构建判别前缀路径集。

    遇终止元素（表达式黑盒/语句/块）即截断该路径——前缀只覆盖"能区分候选"
    的部分，句内剩余内容由变长前瞻在边界块内直接看实际 token。
    """
    result: set[tuple[str, ...]] = {()}
    for feat in prods:
        sub = _feat_token_paths(feat, tree)
        if sub is None:
            break  # 终止元素 → 路径到此为止
        result = {
            p + s for p in result for s in sub if len(p) + len(s) <= _MAX_PREFIX_LEN
        }
    return result


def _paths_prefix_match(seen: list[str], entry: dict) -> bool:
    """实际序列 seen 与判别路径的公共前缀一致 → 候选存活。

    双向匹配：seen 可能比路径短（块规则头 automatic 只是完整路径的前缀），也可能
    比路径长（判别点后的内容不影响归属）。
    """
    return any(
        tuple(seen)[: min(len(seen), len(p))] == p[: min(len(seen), len(p))]
        for p in entry.get("paths", ())
    )


def _filter_by_prefix(
    path_entries: list[dict], seen: list[str]
) -> tuple[list[dict], list[str]]:
    """按公共前缀过滤候选：返回 (存活, 被淘汰名字列表)。"""
    kept = [e for e in path_entries if _paths_prefix_match(seen, e)]
    dropped = [e["name"] for e in path_entries if e not in kept]
    return kept, dropped


def _is_unique_path_hit(
    path_entries: list[dict], seen: list[str], l2_only: list[dict]
) -> bool:
    """唯一 path 候选且 seen 恰好等于其某条**完整**判别路径 → 命中。"""
    if l2_only or len(path_entries) != 1:
        return False
    return any(
        len(p) == len(seen) and p == tuple(seen)
        for p in path_entries[0].get("paths", ())
    )


def _prefer_trial(
    best: tuple[int, int, str] | None, errs: int, consumed: int
) -> bool:
    """Level 2 的 best 选择：errs 最少优先；**仅 errs==0（完整匹配）时**用 consumed 加分。

    2026-08-28 坏输入收敛：errs>0 的错误恢复推进（skip 跳过坏 token）是假推进——
    SimCtrlStmt（inline 分派器，choice 失败 strict 报错+跳过 1 token）凭 consumed=1
    胜过 AssignStmt（表达式失败不推进 consumed=0），`assign a = ;` 被误分类为
    SimCtrlStmt、phase-expr 期望不命中。errs>0 时保持注册顺序（keyword_map[assign]
    首位 AssignStmt 胜，checker 报精确诊断）。
    """
    if best is None or errs < best[0]:
        return True
    return errs == best[0] and errs == 0 and consumed > best[1]


def _has_info_flag(info: object, flag: str) -> bool:
    """规则表条目是否带某标志（条目可能不是 dict）。"""
    return isinstance(info, dict) and bool(info.get(flag))


def _collect_block_ends(tree: dict) -> frozenset[str]:
    """块结束符集合（从块规则 `block_end` 收集，Level 1 前瞻边界）。"""
    return frozenset(
        info["block_end"] for info in tree.values() if _has_info_flag(info, "block_end")
    )


def _collect_stmt_ends(tree: dict) -> frozenset[str]:
    """句子结束符：语句规则 production 末尾字面 token ∪ 所有块规则的 block_end。

    不假设分号——分号只是其中普通成员，随语言配置变化。并入 block_end 是因为
    块结束符天然是容器语句边界：discovery 的 `_skip_to_end` 依赖它正确定位
    if/for 等嵌套容器的终止点——缺失时 if 块边界会延伸到后续语句（吞掉后续
    always 等），语句边界错乱。
    """
    ends = {
        tok
        for info in tree.values()
        if _has_info_flag(info, "is_statement")
        for tok in LookaheadTable._rule_end_tokens(info)
    }
    return frozenset(ends) | _collect_block_ends(tree)


def _is_inline_dispatcher(info: dict, prods: list[dict]) -> bool:
    """inline 语句分派器（production 单 choice of calls，如 SimCtrlStmt）→ 不注册。

    2026-08-28 坏输入收敛：分派器的 first = 各分支 first 并集，注册产生消歧噪音
    ——`assign` 触发 SimCtrlStmt（分支 ProcAssign 的 first），choice 内 strict=False
    使 @PrimaryExpr 失败不推进、后续元素继续假成功（errs=0），`assign = b;` 被误
    分类为 SimCtrlStmt 漏检。分派器只服务 parser 的注入点（@CtrlStmt），分支各自
    是 is_statement 已注册（ProcAssign/DeassignStmt 等），linter 直接命中分支即可。
    """
    return bool(
        info.get("inline") and len(prods) == 1 and prods[0].get("type") == "choice"
    )


class LookaheadTable:
    """从规则树预计算的前瞻消歧表。"""

    def __init__(
        self,
        tree: dict,
        matcher=None,
        trace: bool | None = None,
    ) -> None:
        self._tree = tree
        self._matcher = matcher
        # 消歧 trace（默认环境变量 TPC_LINT_TRACE；显式传值覆盖）
        self._trace = _TRACE_ENV if trace is None else trace
        # 块结束符 / 句子结束符（推导规则见 _collect_block_ends/_collect_stmt_ends）
        self._block_ends = _collect_block_ends(tree)
        self._stmt_ends = _collect_stmt_ends(tree)
        # 方括号开/闭类型（配置推导）：Level 1 括号配对跳过 @PrimaryExpr 内部/
        # 块头范围的 [..] 区间，不参与判别 token 匹配。
        self._l_square, self._r_square = _square_bracket_lr()

        self.keyword_map: dict[str, list[dict]] = {}
        # B 类：标识符触发的候选（单一全局集合，不按上下文分组——上下文分组
        # 是冗余的：所有块内上下文共享同一组 B 类候选，靠 Level 1 前瞻/Level 2
        # 试解析精确筛选，context 参数不参与筛选）
        self.ident_candidates: list[dict] = []
        self._build()

    @staticmethod
    def _rule_end_tokens(info: dict) -> set[str]:
        """规则 production 末尾字面 token（解包 optional）。

        end_case 已移除——语句终点由 production 结构推导（末尾字面 token
        是句子天然结束边界），块结束符由 block_end 收集另入 _stmt_ends。
        """
        result: set[str] = set()
        prods = info.get("prods", [])
        if prods:
            last = prods[-1]
            if isinstance(last, dict):
                if last.get("type") == "optional":
                    last = last.get("elem") or {}
                if last.get("type") == "token" and last["token_type"] not in _TRIVIA:
                    tt = last["token_type"]
                    # 多候选 token（keyword.case|casex）拆为精确成员——含 "|"
                    # 的整串匹配不到实际 token，拆分供 discovery/_skip_to_end
                    # 与 _skip_to_statement_end 的精确匹配使用。
                    result.update(split_token_types(tt))
        return result

    def _build(self) -> None:
        """遍历规则表，按触发形态把候选注册进 `keyword_map` / `ident_candidates`。

        三个注册路径各自的判据与理由见 `_register_block_rule` /
        `_register_ident_rule` / `_register_keyword_rule`。
        """
        for name, info in self._tree.items():
            if self._register_block_rule(name, info):
                continue
            if not info.get("is_statement"):
                continue
            prods = info.get("prods")
            if not prods:
                continue  # 空 production 的 block 块（GenerateBlock 等）由边界检查处理
            if _is_inline_dispatcher(info, prods):
                continue
            firsts = _rule_first(name, self._tree)
            if not firsts:
                continue
            if "id" in firsts:
                self._register_ident_rule(name, prods, firsts)
            else:
                self._register_keyword_rule(name, prods, firsts)

    def _register_block_rule(self, name: str, info: dict) -> bool:
        """块规则：`block.start` 优先注册为起始 token（返回是否已处理）。

        ModuleDecl 等块语句的 production 首元素是 @Identifier（模块名），真实起始
        token 是 block.start（keyword.module）——不注册则无法发现。块规则不要求
        is_statement（generate 等非语句块同样需被发现）。

        注册前把 block_start 还原到 production 首元素：块规则（task/function）
        的 prods 已剥离 keyword.task 等，还原后与普通 A 类规则视图统一
        （prods[0] 都是触发 token），paths 统一从 prods[1:] 开始。
        """
        bs = info.get("block_start") or ""
        if not bs:
            return False
        full = [{"type": "token", "token_type": bs}] + (info.get("prods") or [])
        self.keyword_map.setdefault(bs, []).append(
            {"name": name, "paths": self._a_prefix_paths(full)}
        )
        return True

    def _register_ident_rule(
        self, name: str, prods: list[dict], firsts: set[str]
    ) -> None:
        """B 类：标识符触发 → 前缀路径 + 注册到全局候选（不按上下文分组）。"""
        # 去空路径：仅 epsilon（无判别前缀）→ 视同无静态前缀，走 Level 2
        paths = {p for p in _build_prefix_paths(prods[1:], self._tree) if p}
        self.ident_candidates.append({"name": name, "paths": paths})
        # 同一规则还可能以非 id 字面 token 起始（如拼接赋值 lvalue 的 `{`，
        # 来自 @PrimaryExpr 的 Concatenation 分支）→ 这些起始 token 一并注册到
        # keyword_map，否则 `{a,b} = expr;` 从 `{` 触发不了 BlockingAssign，
        # bracket 分支会整体跳过导致 RHS 误判为新语句。
        for tt in firsts - {"id"}:
            self.keyword_map.setdefault(tt, []).append(
                {"name": name, "paths": paths}
            )

    def _register_keyword_rule(
        self, name: str, prods: list[dict], firsts: set[str]
    ) -> None:
        """A 类：关键字/具体符号触发 → 前缀路径（与 B 类统一两级消歧）。"""
        entry = {"name": name, "paths": self._a_prefix_paths(prods)}
        for tt in firsts:
            self.keyword_map.setdefault(tt, []).append(entry)

    def _a_prefix_paths(self, prods: list[dict]) -> set[tuple[str, ...]]:
        """A 类/块规则的前缀路径（production 视图统一：prods[0] 是触发 token）。

        块规则的 block_start 已由 _build 还原为 prods[0]，普通 A 类规则 prods[0]
        本就是触发 token（keyword.if 等）——统一从 prods[1:] 开始计算判别路径。
        """
        return {p for p in _build_prefix_paths(prods[1:], self._tree) if p}

    def _trace_out(self, msg: str) -> None:
        """消歧决策 trace（stderr，ASCII）。默认关闭。"""
        if self._trace:
            print(f"[lint-trace] {msg}", file=sys.stderr)

    def classify(self, tokens: list[Token], i: int) -> list[str] | None:
        """统一两级消歧：A/B 类候选都走同一套管线。

        Level 1（变长前瞻）：首 token 相同逐 token 预视缩小候选，直到唯一。
        Level 2（试解析）：候选生成式复杂/边界内未收敛 → 完整 production 试解析。
        返回：
            None       = 无候选（非语句起点，discovery 静默跳过）。
            [name, ..] = 候选命中（注册节点供检查）。
            []         = 有语句起点特征但无任何已知规则匹配（拼错关键字/残缺
                         结构头）——discovery 据此报"未识别语句"，不静默吞错。
        """
        tok_type = tokens[i].type
        # 收集候选 entries（A 类 keyword_map / B 类 ident_candidates，结构一致）
        entries: list[dict] | None = None
        if tok_type in self.keyword_map:
            entries = self.keyword_map[tok_type]
        elif tok_type == "id":
            entries = self.ident_candidates
        if not entries:
            self._trace_out(f"classify pos={i} tok={tok_type} -> None (no candidates)")
            return None
        if len(entries) == 1:
            self._trace_out(
                f"classify pos={i} tok={tok_type} -> [{entries[0]['name']}] (unique)"
            )
            return [entries[0]["name"]]  # 唯一候选，无需消歧
        self._trace_out(
            f"classify pos={i} tok={tok_type} entries={[e['name'] for e in entries]}"
        )
        result = self._resolve_ident(
            tokens, i, entries, is_keyword=tok_type in self.keyword_map
        )
        self._trace_out(f"classify pos={i} tok={tok_type} -> {result}")
        return result

    def _resolve_ident(
        self,
        tokens: list[Token],
        i: int,
        entries: list[dict],
        *,
        is_keyword: bool = False,
    ) -> list[str] | None:
        """Level 1：变长前瞻逐 token 淘汰候选，直到唯一且完整路径验证。

        空 paths 候选（无静态前缀可判）不参与淘汰，单独留到 Level 2 试解析，
        避免其空集导致其它候选提前收敛误判。命中要求候选唯一且 seen 恰好
        等于其一条完整判别路径（前缀匹配不命中——防止 `#(` 误判参数实例化）。
        """
        n = len(tokens)
        limit = self._find_boundary(tokens, i + 1, n)
        l2_only: list[dict] = [e for e in entries if not e.get("paths")]
        path_entries: list[dict] = [e for e in entries if e.get("paths")]
        seen: list[str] = []
        # C2 重构（2026-08-28）：消歧决策状态机化——Level 1 扫描（逐 token
        # 淘汰，循环内提前决策）与循环后决策（按 seen/l2_only/path 存活状态
        # 分表）分离，替代原单函数 ~110 行的分支串。
        early = self._level1_scan(
            tokens, i, n, limit, entries, l2_only, path_entries, seen
        )
        if early is not None:
            return early  # 循环内已决策（fallback L2 / 唯一命中）
        return self._level1_decide(
            tokens, i, n, limit, entries, l2_only, path_entries, seen, is_keyword
        )

    def _level1_scan(
        self,
        tokens: list[Token],
        i: int,
        n: int,
        limit: int,
        entries: list[dict],
        l2_only: list[dict],
        path_entries: list[dict],
        seen: list[str],
    ) -> list[str] | None:
        """Level 1 变长前瞻扫描：逐 token 淘汰候选。

        返回 None = 未决策（循环自然结束/break，由 _level1_decide 收尾）；
        返回 list = 循环内已决策（fallback Level 2 / 唯一 path 命中）。
        path_entries/seen 就地更新（decide 消费最终存活状态）。
        """
        pos = i + 1
        while pos < limit:
            if tokens[pos].type in _TRIVIA:
                pos += 1
                continue
            skip = self._square_skip_end(tokens, pos, n)
            if skip > pos:
                pos = skip
                continue
            seen.append(tokens[pos].type)
            kept, dropped = _filter_by_prefix(path_entries, seen)
            path_entries[:] = kept
            self._trace_out(
                f"  L1 pos={pos} tok={tokens[pos].type} seen={seen} "
                f"kept={[e['name'] for e in path_entries]}"
                + (f" dropped={dropped}" if dropped else "")
            )
            if not path_entries and not l2_only:
                return self._fallback_l2(tokens, i, entries, limit, n)
            if _is_unique_path_hit(path_entries, seen, l2_only):
                self._trace_out(f"  L1 -> unique path hit {path_entries[0]['name']}")
                return [path_entries[0]["name"]]
            if not path_entries:
                self._trace_out("  L1 -> path exhausted (l2_only remains), break")
                break  # 只剩需试解析的候选 → 走 Level 2
            pos += 1
        return None

    def _square_skip_end(self, tokens: list[Token], pos: int, n: int) -> int:
        """`[` 处的括号配对跳过终点；不是 `[` 或未闭合 → 返回 pos（不跳过）。

        操作数/范围延续：`[` 是 @PrimaryExpr 内部（a[i]）或块头范围（[7:0]）的
        括号区间，用括号配对跳过、不参与判别 token 匹配——否则 data[i] = i 的
        [i]、function [7:0] 的 [7:0] 让判别路径不匹配而漏检。括号未闭合（残缺）
        → 不跳过，保守加入 seen 走淘汰（不吞错）。
        """
        if tokens[pos].type != self._l_square:
            return pos
        end = self._skip_square(tokens, pos, n)
        return end if end > pos else pos

    def _fallback_l2(
        self, tokens: list[Token], i: int, entries: list[dict], limit: int, n: int
    ) -> list[str] | None:
        """Level 1 判别路径被挡 → Level 2 对原始候选完整 production 试解析。

        判别不了不等于未识别（如拼接 lvalue `{a,b} = expr;` 的起点非 id）；残缺
        语句试解析仍零匹配返回 []，不吞错。`allow_partial=False`：静态可判别的
        多候选（如 if 缺括号的 IfBlock/IfStmt）保持 [] 未识别诊断（e09/e17
        门禁基线）。
        """
        self._trace_out("  L1 -> all path candidates dropped, fallback L2")
        return self._try_parse(tokens, i, entries, min(limit + 1, n))

    def _level1_decide(
        self,
        tokens: list[Token],
        i: int,
        n: int,
        limit: int,
        entries: list[dict],
        l2_only: list[dict],
        path_entries: list[dict],
        seen: list[str],
        is_keyword: bool,
    ) -> list[str] | None:
        """Level 1 循环后决策（C2 重构）：按 seen/l2_only/path 存活状态分表。

        三段：
          - 无判别 token（seen 空）→ 裸 id None / keyword L2 allow_partial
          - 有 l2_only 候选 → L2 试解析**原始** entries（操作数内部 token 可
            能误淘汰真候选，见下）
          - 仅 path 候选 → 唯一返回 / 空 [] / 多候选 L2
        """
        if not seen:
            # 无判别 token 的 B 类裸 id（`id;`）→ 无法确认语句起点，None。
            # A 类（keyword 触发）起始 token 即语句特征——残缺声明（`wire ;`
            # 双候选场景）走 Level 2 试解析：零匹配返回 []（未识别诊断），
            # 部分匹配返回候选（checker 报精确诊断），不静默漏检。
            if is_keyword:
                t_limit = min(limit + 1, n)
                self._trace_out(
                    "  L1 -> no discriminant token (keyword), L2 allow_partial"
                )
                return self._try_parse(
                    tokens, i, entries, t_limit, allow_partial=True
                )
            self._trace_out("  L1 -> no discriminant token (bare id) -> None")
            return None

        # 试解析的匹配上界需含终止符（分号在 limit 位置，多取一个 token 才能
        # 消费句子结束符，否则 TaskDeclOld 的 `;` 超出区间而失败）
        t_limit = min(limit + 1, n)
        if l2_only:
            # 用**原始** entries 试解析（2026-08-28，a[0].b 交错形态暴露的
            # 既有缺陷）：Level 1 淘汰是"seen 与判别路径前缀失配"，但层级
            # 引用 `.`/拼接 `{..}` 等操作数内部 token 会误淘汰真候选——
            # 原 `path_entries + l2_only` 在 path_entries 全淘汰时只试
            # l2_only，`mem[i].field <= x` / `a.b <= x`（NBA target 为层级
            # 引用）被误判未识别。试解析取"错误最少 + 消费最多"者，静态
            # 判别正确的候选（errs=0）天然胜出，不依赖候选顺序。
            self._trace_out(
                f"  L1 -> boundary, L2 on all {len(entries)} entries "
                f"(allow_partial={is_keyword})"
            )
            return self._try_parse(
                tokens,
                i,
                entries,
                t_limit,
                allow_partial=is_keyword,
            )
        if len(path_entries) == 1:
            self._trace_out(
                f"  L1 -> boundary, single survivor {path_entries[0]['name']}"
            )
            return [path_entries[0]["name"]]
        if not path_entries:
            self._trace_out("  L1 -> boundary, no survivors -> unrecognized []")
            return []  # path 候选耗尽且无 Level 2 候选 → 未识别
        # 多候选未收敛 → Level 2 试解析。全失败保持 []（unrecognized）：
        # 判别路径完整命中的多候选（如 if 缺右括号的 IfBlock/IfStmt 双候选）
        # 是"有语句特征但结构残缺"，未识别诊断比精确诊断更贴近根因
        # （e09/e17 门禁基线）。仅 l2_only 分支（静态前缀无法判别的候选，
        # 如 wire 声明的 WireDecl/NetDecl 双候选）允许部分匹配报精确诊断。
        return self._try_parse(tokens, i, path_entries, t_limit)

    def _try_parse(
        self,
        tokens: list[Token],
        i: int,
        entries: list[dict],
        limit: int,
        *,
        allow_partial: bool = False,
    ) -> list[str] | None:
        """Level 2：对每个候选完整 production 试解析，取错误最少且消费最多者。"""
        matcher = self._matcher
        if matcher is None:
            return None
        best: tuple[int, int, str] | None = None
        for entry in entries:
            trial = self._trial_parse(matcher, entry, tokens, i, limit)
            if trial is None:
                continue
            errs, consumed = trial
            if _prefer_trial(best, errs, consumed):
                best = (errs, consumed, entry["name"])
        return self._decide_best(best, allow_partial)

    def _trial_parse(
        self, matcher, entry: dict, tokens: list[Token], i: int, limit: int
    ) -> tuple[int, int] | None:
        """单个候选的试解析 → `(errs, consumed)`；不可试（无 production / 抛异常）→ None。

        块规则（task/function 等）：block_start 已从 production 剥离，试解析前先
        消费 block_start token（同 StatementChecker 的做法）。

        probe 模式：本试探的 limit 是人为截断的（句子边界+1），语句区间在 EOF 处
        耗尽是正常截断而非残缺——EOF 报错会把截断试探误判为匹配失败（合法 for
        被报未识别）。上下文管理器（C1 重构）：退出必恢复实例状态（即使匹配内部
        抛异常），消除裸 try/finally 的污染风险。
        """
        name = entry["name"]
        info = self._tree.get(name, {})
        prods = info.get("prods", [])
        if not prods:
            return None
        trial: list = []
        j = i
        bs = info.get("block_start") or ""
        if bs and j < limit and tokens[j].type == bs:
            j += 1
        try:
            with matcher.probe_mode():
                j = matcher.match_rule(tokens, j, prods, trial, limit)
        except Exception:
            self._trace_out(f"  L2 {name} EXC (skipped)")
            return None
        errs = len(trial)
        consumed = j - i
        self._trace_out(
            f"  L2 {name}: errs={errs} consumed={consumed}"
            + (f" first_err={trial[0].message[:60]!r}" if trial else "")
        )
        return errs, consumed

    def _decide_best(
        self, best: tuple[int, int, str] | None, allow_partial: bool
    ) -> list[str] | None:
        """试解析收口：全失败时 A 类（keyword 触发）返回错误最少者供精确诊断。

        B 类保持 []（未识别诊断，拼错关键字场景）；A 类返回错误最少的候选，
        让 checker 报精确诊断（如 `wire ;` 报 expected id 而非 unrecognized）。
        """
        if best is None:
            self._trace_out("  L2 -> no candidate matched")
            return []
        if best[0] == 0:
            self._trace_out(f"  L2 -> {best[2]} (errs=0 consumed={best[1]})")
            return [best[2]]
        if allow_partial:
            self._trace_out(f"  L2 -> best {best[2]} errs={best[0]} (allow_partial)")
            return [best[2]]
        self._trace_out(f"  L2 -> all fail errs={best[0]} -> unrecognized []")
        return []

    def _find_boundary(self, tokens: list[Token], i: int, n: int) -> int:
        """返回从 i 起第一个句子终止符（分号/块结束）的位置（边界块上界）。"""
        j = i
        while j < n:
            t = tokens[j]
            if t.type in self._stmt_ends:
                return j
            j += 1
        return n

    def _skip_square(self, tokens: list[Token], pos: int, n: int) -> int:
        """从 `[` 跳到匹配的 `]` 之后（处理嵌套 [..]）。

        未闭合（遇语句边界/末尾仍无 `]`）返回 pos，让调用方保守处理
        （`[` 加入判别 seen → 不匹配 → 淘汰，不吞错）。
        """
        depth = 0
        j = pos
        while j < n:
            tt = tokens[j].type
            if tt == self._l_square:
                depth += 1
            elif tt == self._r_square:
                depth -= 1
                if depth == 0:
                    return j + 1
            elif tt in self._stmt_ends:
                return pos  # 越界（未闭合）→ 保守
            j += 1
        return pos

    def is_statement(self, rule: str) -> bool:
        info = self._tree.get(rule, {})
        return bool(info.get("is_statement"))
