"""lookahead.py — 动态前瞻消歧表。

从规则树（build_slice_tree 产物）预计算，供发现阶段（discovery）使用：

    1. keyword_map  — 具体 token 类型 → 规则名列表（A 类：关键字/具体符号触发）
    2. ident_rules   — 标识符触发的规则（B 类），每条含判别 token 集 + 适用上下文
    3. context_leaves — 各块上下文（模块体/过程体）可出现的语句叶子规则集合

B 类消歧 = 动态两级（变长前瞻 + 试解析兜底）：
    - Level 1（变长前瞻）：首 token 相同时逐 token 预视，每预视一个就缩小
      候选路径集，直到只剩唯一一条（前瞻深度到语句边界块为止，不穿透）。
    - Level 2（试解析）：候选生成式含深层 call / 前缀无法静态表达 / 边界内
      未收敛时，对每个候选用完整 production 试解析匹配（复用 RuleMatcher），
      比较匹配结果（错误数 + 消费位置）定夺。
    例如 `foo` 在过程体：
        foo = ...   → BlockingAssign（前缀 ["="]）
        foo <= ...  → NonBlockingAssign（前缀 ["<="]）
        foo(...)    → SubroutineCall（前缀 ["("]）
        foo u1(...) → ModuleInst（前缀 [id, "("]，需预视 2 token）
"""

from __future__ import annotations

from core.define import Token

from ._constants import SEMICOLON_TOKEN_TYPE, TRIVIA as _TRIVIA
from .checker import CTX_MODULE_BODY, CTX_PROC_BODY
from .grammar_slicer import _collect_first_start_tokens


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


def _collect_calls(feat: dict | None) -> list[str]:
    """收集一个 feature 中引用的所有子规则名（用于展开选择器）。"""
    if feat is None:
        return []
    typ = feat.get("type")
    if typ == "call":
        return [feat["name"]]
    if typ == "choice":
        result: list[str] = []
        for alt in feat.get("alternatives", []):
            result += _collect_calls(alt)
        return result
    if typ == "seq":
        result = []
        for item in feat.get("items", []):
            result += _collect_calls(item)
        return result
    if typ in ("optional", "repeat", "plus"):
        return _collect_calls(feat.get("elem"))
    return []


def _is_pure_call_choice(feat: dict | None) -> bool:
    """feature 是否纯 @ 分派：call 或 choice-of-calls（无 token/repeat 等）。"""
    if feat is None:
        return False
    typ = feat.get("type")
    if typ == "call":
        return True
    if typ == "choice":
        return all(
            _is_pure_call_choice(a) for a in feat.get("alternatives", [])
        )
    return False


def _expand_selector(name: str, tree: dict, acc: set[str], visited: set[str]) -> None:
    """递归展开选择器规则（inline 分发），收集叶子语句规则名。

    选择器 = production 仅 1 个元素且为纯 @ 分派（如 Stmt → @A|@B|@C）。
    遇含具体 token 的叶子语句（BlockingAssign 等）即停止加入，不继续展开
    到表达式原子（与 is_statement 显式标记的规则集合对齐）。
    """
    if name in visited:
        return
    visited.add(name)
    info = tree.get(name)
    if not info or not info.get("prods"):
        return
    prods = info["prods"]
    if len(prods) == 1 and _is_pure_call_choice(prods[0]):
        for c in _collect_calls(prods[0]):
            _expand_selector(c, tree, acc, visited)
    else:
        acc.add(name)


def _context_leaves(tree: dict, root_name: str) -> set[str]:
    """展开根选择器规则，返回其下所有叶子语句规则名集合。"""
    acc: set[str] = set()
    _expand_selector(root_name, tree, acc, set())
    return acc


# 表达式黑盒：带 pratt 标识的规则（Expression/运算符链）由 pratt 解析器专门处理，
# first 是 id（与触发相同）或内部复杂，前缀无判别价值。作为"终止元素"：
# 路径在此结束，不继续展开其后的 token。按 pratt 标识识别而非硬编码规则名
# （换一套语法配置，表达式规则即使改名也带 pratt=true）。
# 前缀路径最大长度（防御；真实判别前缀都很短，到边界块即止）
_MAX_PREFIX_LEN = 8


def _feat_token_paths(
    feat: dict | None, tree: dict
) -> set[tuple[str, ...]] | None:
    """单个 production 元素的判别 token 序列集。

    返回 set[tuple[str, ...]]：该元素可能的前缀 token 序列（含空元组 = epsilon）。
    返回 None：该元素是**终止元素**（表达式黑盒/语句/块边界）——路径在此结束，
    不继续展开其后的 token。前缀在此截断，后续由变长前瞻在边界块内区分。
    """
    if feat is None:
        return {()}
    typ = feat.get("type")
    if typ == "token":
        return {(feat["token_type"],)}
    if typ == "choice":
        result: set[tuple[str, ...]] = set()
        for alt in feat.get("alternatives", []):
            sub = _feat_token_paths(alt, tree)
            if sub is None:
                return None  # 任一分支含终止元素 → 整体终止
            result |= sub
        return result
    if typ == "seq":
        result = {()}
        for item in feat.get("items", []):
            sub = _feat_token_paths(item, tree)
            if sub is None:
                return result  # seq 遇终止元素 → 保留到该元素为止的前缀
            result = {p + s for p in result for s in sub}
        return result
    if typ == "optional":
        elem = feat.get("elem")
        sub = _feat_token_paths(elem, tree)
        if sub is None:
            return None  # 可选复杂 call → 截断（内容不可静态判别）
        return {()} | sub
    if typ in ("repeat", "plus"):
        # 变长重复：0 次 或 1 次（再长不增加判别深度，到边界块为止）
        elem = feat.get("elem")
        sub = _feat_token_paths(elem, tree)
        if sub is None:
            return None
        return {()} | sub
    if typ == "call":
        name = feat.get("name", "")
        info = tree.get(name)
        if info is None:
            return None
        if info.get("pratt"):
            return None  # pratt 表达式黑盒（由 pratt 解析器处理）→ 终止元素
        if info.get("is_statement") or info.get("is_block"):
            return None  # 语句/块边界 → 终止元素（不穿透句子级）
        if not info.get("is_atom"):
            return None  # 非原子复杂 call（参数列表/端口连接等）→ 截断，走 Level 2
        prods = info.get("prods", [])
        if not prods:
            return None
        return {(t,) for t in _collect_first_start_tokens(prods[0], tree)}
    return {()}


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
            p + s
            for p in result
            for s in sub
            if len(p) + len(s) <= _MAX_PREFIX_LEN
        }
    return result


class LookaheadTable:
    """从规则树预计算的前瞻消歧表。"""

    def __init__(
        self,
        tree: dict,
        module_item_rule: str,
        stmt_rule: str,
        matcher=None,
    ) -> None:
        self._tree = tree
        self._matcher = matcher
        # fail-fast：语句入口选择器名（pyv.toml [linter] module_item_rule/stmt_rule）
        # 必须存在于规则树。代码不硬编码任何语法规则名——换一套配置即失效；
        # 名字缺失/失效在此直接抛错，而非 _context_leaves 静默返回空集导致
        # B 类 ident 候选全部消失（ModuleInst 等漏检），那是静默降级。
        for _name, _role in (
            (module_item_rule, "linter.module_item_rule（模块体语句入口）"),
            (stmt_rule, "linter.stmt_rule（过程体语句入口）"),
        ):
            if _name not in tree:
                raise RuntimeError(
                    f"[linter] 语句入口选择器规则 '{_name}'（{_role}）不存在于语法规则树。"
                    "请检查 pyv.toml [linter] 配置与语法规则命名是否一致。"
                )
        self._module_leaves = _context_leaves(tree, module_item_rule)
        self._proc_leaves = _context_leaves(tree, stmt_rule)
        # 句子终止符（边界块）：分号 + 块结束，Level 1 前瞻上界
        self._block_ends = frozenset(
            info["block_end"]
            for info in tree.values()
            if isinstance(info, dict) and info.get("block_end")
        )

        self.keyword_map: dict[str, list[dict]] = {}
        # B 类：context → 候选子集（变长，不预写死 key，get 默认空）
        self.ident_by_ctx: dict[str, list[dict]] = {}
        self._build()

    def _build(self) -> None:
        for name, info in self._tree.items():
            # 块起始 token（block.start）优先注册为起始 token：
            # ModuleDecl 等块语句的 production 首元素是 @Identifier（模块名），
            # 真实起始 token 是 block.start（keyword.module），不注册则无法发现。
            # 块规则不要求 is_statement（generate 等非语句块同样需被发现）。
            bs = info.get("block_start") or ""
            if bs:
                # 还原 block_start 到 production 首元素：块规则（task/function）
                # 的 prods 已剥离 keyword.task 等，还原后与普通 A 类规则视图统一
                # （prods[0] 都是触发 token），paths 统一从 prods[1:] 开始。
                bprods = info.get("prods") or []
                full = [{"type": "token", "token_type": bs}] + bprods
                bpaths = self._a_prefix_paths(full)
                self.keyword_map.setdefault(bs, []).append(
                    {"name": name, "paths": bpaths}
                )
                continue

            if not info.get("is_statement"):
                continue
            prods = info.get("prods")
            if not prods:
                continue  # 空 production 的 block 块（GenerateBlock 等）由边界检查处理
            firsts = _rule_first(name, self._tree)
            if not firsts:
                continue
            if "id" in firsts:
                # B 类：标识符触发 → 前缀路径 + 按上下文归属（变长子集）
                paths = _build_prefix_paths(prods[1:], self._tree)
                # 去空路径：仅 epsilon（无判别前缀）→ 视同无静态前缀，走 Level 2
                paths = {p for p in paths if p}
                entry = {"name": name, "paths": paths}
                if name in self._module_leaves:
                    self.ident_by_ctx.setdefault(CTX_MODULE_BODY, []).append(entry)
                if name in self._proc_leaves:
                    self.ident_by_ctx.setdefault(CTX_PROC_BODY, []).append(entry)
            else:
                # A 类：关键字/具体符号触发 → 也计算前缀路径（与 B 类统一两级消歧）
                apaths = self._a_prefix_paths(prods)
                entry = {"name": name, "paths": apaths}
                for tt in firsts:
                    self.keyword_map.setdefault(tt, []).append(entry)

    def _a_prefix_paths(self, prods: list[dict]) -> set[tuple[str, ...]]:
        """A 类/块规则的前缀路径（production 视图统一：prods[0] 是触发 token）。

        块规则的 block_start 已由 _build 还原为 prods[0]，普通 A 类规则 prods[0]
        本就是触发 token（keyword.if 等）——统一从 prods[1:] 开始计算判别路径。
        """
        return {p for p in _build_prefix_paths(prods[1:], self._tree) if p}

    def classify(self, tokens: list[Token], i: int, context: str) -> list[str] | None:
        """统一两级消歧：A/B 类候选都走同一套管线。

        Level 1（变长前瞻）：首 token 相同逐 token 预视缩小候选，直到唯一。
        Level 2（试解析）：候选生成式复杂/边界内未收敛 → 完整 production 试解析。
        返回 None = 无候选（非语句起点或未识别语法）。
        """
        tok_type = tokens[i].type
        # 收集候选 entries（A 类 keyword_map / B 类 ident_by_ctx，结构一致）
        entries: list[dict] | None = None
        if tok_type in self.keyword_map:
            entries = self.keyword_map[tok_type]
        elif tok_type == "id":
            entries = self.ident_by_ctx.get(context, [])
        if not entries:
            return None
        if len(entries) == 1:
            return [entries[0]["name"]]  # 唯一候选，无需消歧
        return self._resolve_ident(tokens, i, entries)

    def _resolve_ident(
        self, tokens: list[Token], i: int, entries: list[dict]
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
        pos = i + 1
        while pos < limit:
            if tokens[pos].type in _TRIVIA:
                pos += 1
                continue
            seen.append(tokens[pos].type)
            kept: list[dict] = []
            for entry in path_entries:
                # 匹配：实际序列 seen 与判别路径公共前缀一致（双向——seen 可能比
                # 路径短，如块规则头 automatic 只是完整路径的前缀；也可能比路径长，
                # 判别点后的内容不影响归属）
                if any(
                    tuple(seen)[: min(len(seen), len(p))]
                    == p[: min(len(seen), len(p))]
                    for p in entry.get("paths", ())
                ):
                    kept.append(entry)
            path_entries = kept
            if not path_entries and not l2_only:
                return None  # 候选清空 → 未识别（Phase 5 报错，先跳过）
            # 命中：唯一 path 候选且 seen 恰好等于某条完整判别路径
            if len(path_entries) == 1 and any(
                len(p) == len(seen) and p == tuple(seen)
                for p in path_entries[0].get("paths", ())
            ):
                return [path_entries[0]["name"]]
            if not path_entries:
                break  # 只剩需试解析的候选 → 走 Level 2
            pos += 1
        # 到边界块 / path 候选耗尽
        if not seen:
            return None  # 无任何判别 token（如 `id;`）→ 无法确认是语句起点
        # 试解析的匹配上界需含终止符（分号在 limit 位置，多取一个 token 才能
        # 消费句子结束符，否则 TaskDeclOld 的 `;` 超出区间而失败）
        t_limit = min(limit + 1, n)
        if l2_only:
            return self._try_parse(tokens, i, path_entries + l2_only, t_limit)
        if len(path_entries) == 1:
            return [path_entries[0]["name"]]
        if not path_entries:
            return None
        # 多候选未收敛 → Level 2 试解析
        return self._try_parse(tokens, i, path_entries, t_limit)

    def _try_parse(
        self, tokens: list[Token], i: int, entries: list[dict], limit: int
    ) -> list[str] | None:
        """Level 2：对每个候选完整 production 试解析，取错误最少且消费最多者。"""
        if self._matcher is None:
            return None
        best: tuple[int, int, str] | None = None
        for entry in entries:
            name = entry["name"]
            info = self._tree.get(name, {})
            prods = info.get("prods", [])
            if not prods:
                continue
            trial: list = []
            j = i
            # 块规则（task/function 等）：block_start 已从 production 剥离，
            # 试解析前先消费 block_start token（同 StatementChecker 的做法）。
            bs = info.get("block_start") or ""
            if bs and j < limit and tokens[j].type == bs:
                j += 1
            try:
                j = self._matcher.match_rule(tokens, j, prods, trial, limit)
            except Exception:
                continue
            errs = len(trial)
            consumed = j - i
            if best is None or errs < best[0] or (
                errs == best[0] and consumed > best[1]
            ):
                best = (errs, consumed, name)
        if best is None or best[0] != 0:
            return None  # 全失败 → 未识别
        return [best[2]]

    def _find_boundary(self, tokens: list[Token], i: int, n: int) -> int:
        """返回从 i 起第一个句子终止符（分号/块结束）的位置（边界块上界）。"""
        j = i
        while j < n:
            t = tokens[j]
            if t.type == SEMICOLON_TOKEN_TYPE or t.type in self._block_ends:
                return j
            j += 1
        return n

    def end_case(self, rule: str) -> set[str]:
        info = self._tree.get(rule, {})
        return set(info.get("end_case", set()) or ())

    def is_statement(self, rule: str) -> bool:
        info = self._tree.get(rule, {})
        return bool(info.get("is_statement"))
