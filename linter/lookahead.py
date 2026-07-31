"""lookahead.py — 动态前瞻消歧表。

从规则树（build_slice_tree 产物）预计算，供发现阶段（discovery）使用：

    1. keyword_map  — 具体 token 类型 → 规则名列表（A 类：关键字/具体符号触发）
    2. ident_rules   — 标识符触发的规则（B 类），每条含判别 token 集 + 适用上下文
    3. context_leaves — 各块上下文（模块体/过程体）可出现的语句叶子规则集合

B 类消歧策略（决策 1：动态前瞻逐级缩小范围）：
    - 先用块上下文（骨架树推导）过滤候选集
    - 再前瞻 id 之后的第一个必选 token（判别 token）确定具体规则
    例如 `foo` 在过程体：
        foo = ...   → BlockingAssign（判别 {symbol.base.equal}）
        foo <= ...  → NonBlockingAssign（判别 {symbol.extend.lesser_equal}）
        foo(...)    → SubroutineCall（判别 {bracket.l_parentheses}）
"""

from __future__ import annotations

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


def _expand_selector(name: str, tree: dict, acc: set[str], visited: set[str]) -> None:
    """递归展开选择器规则（inline 分发），收集叶子规则名。"""
    if name in visited:
        return
    visited.add(name)
    info = tree.get(name)
    if not info or not info.get("prods"):
        return
    first = info["prods"][0]
    calls = _collect_calls(first)
    if calls:
        for c in calls:
            _expand_selector(c, tree, acc, visited)
    else:
        acc.add(name)


def _context_leaves(tree: dict, root_name: str) -> set[str]:
    """展开根选择器规则，返回其下所有叶子语句规则名集合。"""
    acc: set[str] = set()
    _expand_selector(root_name, tree, acc, set())
    return acc


def _discriminator(prods: list[dict], tree: dict) -> set[str]:
    """计算 id 开头规则的判别 token 集：id 之后第一个必选元素的 first 集。

    跳过 optional/repeat（它们无强制起始 token），直到遇到有 first 的元素。
    """
    for feat in prods[1:]:
        firsts = _first_of(feat, tree)
        if firsts:
            return firsts
    return set()


class LookaheadTable:
    """从规则树预计算的前瞻消歧表。"""

    def __init__(
        self,
        tree: dict,
        module_item_rule: str = "ModuleItem",
        stmt_rule: str = "Stmt",
    ) -> None:
        self._tree = tree
        self._module_leaves = _context_leaves(tree, module_item_rule)
        self._proc_leaves = _context_leaves(tree, stmt_rule)

        self.keyword_map: dict[str, list[str]] = {}
        self.ident_by_ctx: dict[str, list[dict]] = {
            CTX_MODULE_BODY: [],
            CTX_PROC_BODY: [],
        }
        self._build()

    def _build(self) -> None:
        for name, info in self._tree.items():
            # 块起始 token（block.start）优先注册为起始 token：
            # ModuleDecl 等块语句的 production 首元素是 @Identifier（模块名），
            # 真实起始 token 是 block.start（keyword.module），不注册则无法发现。
            # 块规则不要求 is_statement（generate 等非语句块同样需被发现）。
            bs = info.get("block_start") or ""
            if bs:
                self.keyword_map.setdefault(bs, []).append(name)
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
                # B 类：标识符触发 → 归类到适用上下文 + 判别 token
                disc = _discriminator(prods, self._tree)
                if not disc:
                    continue
                entry = {"name": name, "discriminator": disc}
                if name in self._module_leaves:
                    self.ident_by_ctx[CTX_MODULE_BODY].append(entry)
                if name in self._proc_leaves:
                    self.ident_by_ctx[CTX_PROC_BODY].append(entry)
            else:
                # A 类：关键字/具体符号触发
                for tt in firsts:
                    self.keyword_map.setdefault(tt, []).append(name)

    def classify(self, tok_type: str, nxt_type: str, context: str) -> list[str] | None:
        """消歧：根据当前 token、下一 token、块上下文，返回候选规则名列表。

        返回 None 表示无候选（当前 token 不是语句起点）。
        """
        # 1. 关键字/具体符号触发
        if tok_type in self.keyword_map:
            return self.keyword_map[tok_type]

        # 2. 标识符触发 → 上下文过滤 + 判别 token 前瞻
        if tok_type == "id":
            for entry in self.ident_by_ctx.get(context, []):
                if nxt_type in entry["discriminator"]:
                    return [entry["name"]]
        return None

    def end_case(self, rule: str) -> set[str]:
        info = self._tree.get(rule, {})
        return set(info.get("end_case", set()) or ())

    def is_statement(self, rule: str) -> bool:
        info = self._tree.get(rule, {})
        return bool(info.get("is_statement"))
