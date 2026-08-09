"""lookahead.py — 动态前瞻消歧表。

从规则树（build_slice_tree 产物）预计算，供发现阶段（discovery）使用：

    1. keyword_map  — 具体 token 类型 → 规则名列表（A 类：关键字/具体符号触发）
    2. ident_by_ctx  — 标识符触发的规则（B 类），每条含判别前缀路径集，注册到
       opener_context 动态生成的块内上下文名集合（_ctx_names）

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

from core.utils import square_bracket_types


# 通用词法常量（语言无关，自包含于引用处；原 linter/_constants.py 已删）
_TRIVIA = frozenset({"space.fold", "space", "comment", "newline"})
from .grammar_slicer import _collect_first_start_tokens

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
        if sub is None and elem is not None and elem.get("type") == "call":
            # 可选复杂 call：仅当 first 含 `[`（可被 Level 1 括号配对跳过，如
            # @Range? 的 [7:0]）时保留 epsilon + first 集——否则 function [7:0]
            # 的 [ 不在判别路径（A 类多候选消歧被淘汰）而漏检。其他复杂 call
            # （如 @ParamOverride? 的 #(...)，Level 1 无法跳过其内部）维持截断
            # → paths 空走 Level 2 试解析，避免 # 后的 ( 逐 token 误淘汰。
            info = tree.get(elem.get("name", "")) or {}
            prods = info.get("prods") or []
            if prods:
                firsts = {t for t in _collect_first_start_tokens(prods[0], tree)}
                if _square_bracket_lr()[0] in firsts:
                    return {()} | {(t,) for t in firsts}
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
            p + s for p in result for s in sub if len(p) + len(s) <= _MAX_PREFIX_LEN
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
        opener_ctx: dict[str, str] | None = None,
    ) -> None:
        self._tree = tree
        self._matcher = matcher
        # fail-fast：语句入口选择器名（tpc.toml [linter] module_item_rule/stmt_rule）
        # 必须存在于规则树。代码不硬编码任何语法规则名——换一套配置即失效；
        # 名字缺失/失效在此直接抛错，而非静默返回空集导致 B 类 ident 候选
        # 全部消失（ModuleInst 等漏检），那是静默降级。
        for _name, _role in (
            (module_item_rule, "linter.module_item_rule（模块体语句入口）"),
            (stmt_rule, "linter.stmt_rule（过程体语句入口）"),
        ):
            if _name not in tree:
                raise RuntimeError(
                    f"[linter] 语句入口选择器规则 '{_name}'（{_role}）不存在于语法规则树。"
                    "请检查 tpc.toml [linter] 配置与语法规则命名是否一致。"
                )
        # 块内上下文名集合（从 opener_context 配置动态生成，不硬编码
        # module_body/proc_body 等 Verilog 结构名——换语言由配置决定）
        self._ctx_names = frozenset(opener_ctx.values()) if opener_ctx else frozenset()
        # 块结束符集合（从块规则 block_end 收集，Level 1 前瞻边界）
        self._block_ends = frozenset(
            info["block_end"]
            for info in tree.values()
            if isinstance(info, dict) and info.get("block_end")
        )
        # 句子结束符（从语句规则 production 末尾字面 token + 配置 end_case 推导，
        # 不假设分号——分号只是其中普通成员，随语言配置变化）
        self._stmt_ends = frozenset(
            tok
            for info in tree.values()
            if isinstance(info, dict) and info.get("is_statement")
            for tok in LookaheadTable._rule_end_tokens(info)
        )
        # 方括号开/闭类型（配置推导）：Level 1 括号配对跳过 @PrimaryExpr 内部/
        # 块头范围的 [..] 区间，不参与判别 token 匹配。
        self._l_square, self._r_square = _square_bracket_lr()

        self.keyword_map: dict[str, list[dict]] = {}
        # B 类：context → 候选子集（变长，不预写死 key，get 默认空）
        self.ident_by_ctx: dict[str, list[dict]] = {}
        self._build()

    @staticmethod
    def _rule_end_tokens(info: dict) -> set[str]:
        """规则 production 末尾字面 token（解包 optional）+ 配置 end_case。

        排除 ! 前缀（排除项）与 trivia（newline 等——trivia 是分隔符，
        非句子结束 token；end_case 里的 newline 表示"语句后可换行"）。
        """
        result = {
            s for s in (info.get("end_case", []) or [])
            if not s.startswith("!") and s not in _TRIVIA
        }
        prods = info.get("prods", [])
        if prods:
            last = prods[-1]
            if isinstance(last, dict):
                if last.get("type") == "optional":
                    last = last.get("elem") or {}
                if last.get("type") == "token" and last["token_type"] not in _TRIVIA:
                    result.add(last["token_type"])
        return result

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
                # B 类：标识符触发 → 前缀路径 + 注册到所有块内上下文（动态生成）
                paths = _build_prefix_paths(prods[1:], self._tree)
                # 去空路径：仅 epsilon（无判别前缀）→ 视同无静态前缀，走 Level 2
                paths = {p for p in paths if p}
                entry = {"name": name, "paths": paths}
                for ctx in self._ctx_names:
                    self.ident_by_ctx.setdefault(ctx, []).append(entry)
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
        返回：
            None       = 无候选（非语句起点，discovery 静默跳过）。
            [name, ..] = 候选命中（注册节点供检查）。
            []         = 有语句起点特征但无任何已知规则匹配（拼错关键字/残缺
                         结构头）——discovery 据此报"未识别语句"，不静默吞错。
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
            # 操作数/范围延续：`[` 是 @PrimaryExpr 内部（a[i]）或块头范围（[7:0]）
            # 的括号区间，用括号配对跳过、不参与判别 token 匹配——否则
            # data[i] = i 的 [i]、function [7:0] 的 [7:0] 让判别路径不匹配而漏检。
            # 括号未闭合（残缺）→ 跳过失败，保守加入 seen 走淘汰（不吞错）。
            if tokens[pos].type == self._l_square:
                end = self._skip_square(tokens, pos, n)
                if end > pos:
                    pos = end
                    continue
            seen.append(tokens[pos].type)
            kept: list[dict] = []
            for entry in path_entries:
                # 匹配：实际序列 seen 与判别路径公共前缀一致（双向——seen 可能比
                # 路径短，如块规则头 automatic 只是完整路径的前缀；也可能比路径长，
                # 判别点后的内容不影响归属）
                if any(
                    tuple(seen)[: min(len(seen), len(p))] == p[: min(len(seen), len(p))]
                    for p in entry.get("paths", ())
                ):
                    kept.append(entry)
            path_entries = kept
            if not path_entries and not l2_only:
                # 候选清空：有语句起点特征但内容不匹配任何已知语句规则
                # （拼错关键字/残缺结构头）→ 空列表表示"未识别"，discovery 报错。
                return []
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
            return []  # path 候选耗尽且无 Level 2 候选 → 未识别
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
            # probe 模式：本试探的 limit 是人为截断的（句子边界+1），语句区间
            # 在 EOF 处耗尽是正常截断而非残缺——EOF 报错会把截断试探误判为匹配
            # 失败（合法 for 被报未识别）。试探语境置 True，真实检查不受影响。
            matcher = self._matcher
            old_probe = matcher._probe_eof
            matcher._probe_eof = True
            try:
                j = matcher.match_rule(tokens, j, prods, trial, limit)
            except Exception:
                continue
            finally:
                matcher._probe_eof = old_probe
            errs = len(trial)
            consumed = j - i
            if (
                best is None
                or errs < best[0]
                or (errs == best[0] and consumed > best[1])
            ):
                best = (errs, consumed, name)
        if best is None or best[0] != 0:
            return []  # 全失败 → 未识别（discovery 据此报错）
        return [best[2]]

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

    def end_case(self, rule: str) -> set[str]:
        info = self._tree.get(rule, {})
        return set(info.get("end_case", set()) or ())

    def is_statement(self, rule: str) -> bool:
        info = self._tree.get(rule, {})
        return bool(info.get("is_statement"))
