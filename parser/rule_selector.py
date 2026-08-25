"""RuleSelector — candidate rule filtering based on start token matching.

Doc: docs/language_walkthrough.md（规则选择/语句发现）
"""

from typing import Any
from core.define import Token, GrammarRule
from core.errors import GrammarError
from ._constants import IDENTIFIER_TOKEN_TYPE


def _compute_start_tokens(
    feat: dict,
    grammar_rules: dict[str, GrammarRule],
    visited: set[str],
) -> set[str]:
    """递归计算一个 feature 可能起始的 token 类型集合 (First set)。"""
    typ = feat.get("type")

    if typ == "token":
        tt = feat.get("token_type", "")
        if "|" in tt:
            return set(tt.split("|"))
        return {tt}

    if typ == "call":
        name = feat.get("name", "")
        if name in visited or name not in grammar_rules:
            return set()
        visited.add(name)
        rule = grammar_rules[name]
        # 块规则的起始 token 由 block 外部负责，不在 First set 计算中
        if getattr(rule, "is_block", False):
            return set()
        prods = rule.prods
        if not prods:
            return set()
        # 只取第一个 production 元素的 First set（后续元素可能不可达）
        try:
            pf = analyze_production_features(prods[0])
        except Exception:
            return set()
        if pf:
            return _compute_start_tokens(pf, grammar_rules, visited.copy())
        return set()

    if typ == "choice":
        alts = feat.get("alternatives", [])
        result: set[str] = set()
        for alt in alts:
            result.update(_compute_start_tokens(alt, grammar_rules, visited.copy()))
        return result

    if typ == "seq":
        items = feat.get("items", [])
        if not items:
            return set()
        return _compute_start_tokens(items[0], grammar_rules, visited.copy())

    if typ in ("repeat", "optional", "plus"):
        elem = feat.get("elem")
        if elem:
            return _compute_start_tokens(elem, grammar_rules, visited.copy())

    return set()


def build_start_token_map_names(
    grammar_rules: dict[str, GrammarRule],
    statement_rule_names: list[str],
) -> dict[str, list[str]]:
    """预计算起始 token → 规则名称列表的映射表（可序列化为 JSON）。"""
    name_map: dict[str, list[str]] = {}
    for name in statement_rule_names:
        if name not in grammar_rules:
            continue
        rule = grammar_rules[name]

        # 补充：block.start 也作为起始 token 注册（优先于 production 处理，
        # 确保空 production 的块规则如 GenerateBlock 仍能注册起始符）
        bs = getattr(rule, "block_start", None)
        if bs:
            name_map.setdefault(bs, []).append(name)

        prods = rule.prods
        if not prods:
            continue
        first_prod_str = prods[0]
        try:
            feat = analyze_production_features(first_prod_str)
        except Exception:
            continue
        if feat is None:
            continue
        starts = _compute_start_tokens(feat, grammar_rules, set())
        for tok in starts:
            if tok not in name_map:
                name_map[tok] = []
            name_map[tok].append(name)
    return name_map


def _hint_rank(name: str, hints: list[str]) -> int:
    """hint 匹配优先级：精确命中或通配后缀命中返回 -1，否则 0。"""
    for hint in hints:
        if hint.startswith("*"):
            if name.endswith(hint[1:]):
                return -1
        elif name == hint:
            return -1
    return 0


class RuleSelector:
    def __init__(
        self,
        grammar_rules: dict[str, GrammarRule],
        statement_rule_names: list[str],
    ):
        self.grammar_rules = grammar_rules
        self.statement_rule_names = statement_rule_names
        self.start_token_map: dict[str, list[str]] = {}
        self._names_to_rules: dict[str, GrammarRule] | None = None

        self.start_token_map = build_start_token_map_names(
            grammar_rules, statement_rule_names
        )

    def select_candidates(
        self,
        token: Token,
        pre_symbols: dict[str, str] | None = None,
        pre_hints: dict[str, list[str]] | None = None,
        scope_lookup_fn=None,
    ) -> list[GrammarRule]:
        if token is None:
            return []
        rule_names = self.start_token_map.get(token.type, [])
        if not rule_names:
            return []
        # 按 statement_rule_names 排序，不在列表中的规则排到最后
        _ORDER_NOT_FOUND = len(self.statement_rule_names)
        order = {name: i for i, name in enumerate(self.statement_rule_names)}
        rule_names.sort(key=lambda n: order.get(n, _ORDER_NOT_FOUND))

        # 预符号提示：如果 token 是 id 且已知符号名，优先匹配相关规则
        if pre_symbols and pre_hints and token.type == IDENTIFIER_TOKEN_TYPE:
            kind = pre_symbols.get(token.content)
            if kind and kind in pre_hints:
                rule_names.sort(key=lambda n: _hint_rank(n, pre_hints[kind]))

        # 运行时作用域查询：如果 scope 中已知此符号种类，也作为 hint
        if scope_lookup_fn is not None and token.type == IDENTIFIER_TOKEN_TYPE:
            scope_kind = scope_lookup_fn(token.content)
            if scope_kind and pre_hints and scope_kind in pre_hints:
                rule_names.sort(key=lambda n: _hint_rank(n, pre_hints[scope_kind]))

        # 名称 → 对象
        result = []
        for name in rule_names:
            if name in self.grammar_rules:
                result.append(self.grammar_rules[name])
        return result

    get_candidate_rules = select_candidates

    def get_block_rule(self) -> str | None:
        # 优先无 block_start 的匿名根块（如 c4 的 Program）——根块由整个 token
        # 流驱动（无显式起止符），而非带 block_start 的具体块规则。回退到
        # 第一个块规则（兼容 Verilog：根是带 block_start 的 ModuleDecl）。
        for rule_name, rule in self.grammar_rules.items():
            if getattr(rule, "is_block", False) and not getattr(
                rule, "block_start", None
            ):
                return rule_name
        for rule_name, rule in self.grammar_rules.items():
            if getattr(rule, "is_block", False):
                return rule_name
        return None


"""Production feature analyzer — detect choice/seq structure in production strings."""

import re

# 预编译正则（避免每次调用 build_tree 重复编译）
_RE_CALL = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_RE_TOKEN = re.compile(r"^[a-zA-Z_\.]+$")

SEPARATOR_HANDLERS = [
    ("|", "choice", "alternatives"),  # 分支优先级最高
    (",", "seq", "items"),  # 序列次之
]

# 后缀运算符映射
SUFFIX_MAP = {
    "+": "plus",
    "*": "repeat",
    "?": "optional",
}

# 测试输出分隔线
_SEPARATOR = "-" * 60


def _flatten_production_features(
    features: dict[str, Any], prefix: str = "",
) -> list[tuple[str, dict[str, Any]]]:
    """将产生式特征树展平为 (path, leaf_feature) 列表。

    path 采用 $N 寻址语法，如：
        choice:  $1, $2, $3
        seq:     $1.$1, $1.$2
        repeat:  内部元素沿用外层路径
    """
    typ = features.get("type")
    if typ in ("token", "call"):
        return [(prefix, features)]
    if typ == "choice":
        result = []
        for i, alt in enumerate(features.get("alternatives", [])):
            p = f"{prefix}.${i + 1}" if prefix else f"${i + 1}"
            result.extend(_flatten_production_features(alt, p))
        return result
    if typ == "seq":
        result = []
        for i, item in enumerate(features.get("items", [])):
            p = f"{prefix}.${i + 1}" if prefix else f"${i + 1}"
            result.extend(_flatten_production_features(item, p))
        return result
    if typ in ("repeat", "plus", "optional"):
        return _flatten_production_features(features.get("elem", {}), prefix)
    return []


def flatten_production_features(
    production: str,
) -> list[tuple[str, dict[str, Any]]]:
    """分析产生式并展平为 (path, leaf_feature) 列表。"""
    features = analyze_production_features(production)
    if features is None:
        return []
    return _flatten_production_features(features)


def analyze_production_features(production: str) -> dict[str, Any] | None:
    """分析产生式字符串，返回纯字典结构的中间 AST。
    支持后缀操作符：
        *  零次或多次 -> {"type": "repeat", "elem": ...}
        +  一次或多次 -> {"type": "plus", "elem": ...}
        ?  零次或一次 -> {"type": "optional", "elem": ...}
    """
    placeholder_map: dict[str, dict[str, Any] | None] = {}

    def find_outermost_paren(s: str) -> tuple[int, int] | None:
        stack = []
        for i, ch in enumerate(s):
            if ch == "(":
                stack.append(i)
            elif ch == ")" and stack:
                start = stack.pop()
                if not stack:
                    return (start, i)
        return None

    def build_tree(s: str) -> dict[str, Any] | None:
        s = s.strip().replace(" ", "")
        if not s:
            return None

        # 1. 括号占位
        paren = find_outermost_paren(s)
        if paren:
            start, end = paren
            before = s[:start]
            inner = s[start + 1 : end]
            after = s[end + 1 :]
            inner_ast = build_tree(inner)
            placeholder = f"__paren_{len(placeholder_map)}__"
            placeholder_map[placeholder] = inner_ast
            new_s = before + placeholder + after
            return build_tree(new_s)

        if s in placeholder_map:
            return placeholder_map[s]

        for sep, typ, field in SEPARATOR_HANDLERS:
            if sep in s:
                parts = [p.strip() for p in s.split(sep) if p.strip()]
                return {
                    "type": typ,
                    field: [build_tree(p) for p in parts if build_tree(p) is not None],
                }

        # 3. 后缀运算符（优先级最高）：'+', '*', '?'
        for suffix, typ in SUFFIX_MAP.items():
            if s.endswith(suffix):
                base = s[:-1].strip()
                return {"type": typ, "elem": build_tree(base)}

        # 4. 语法调用 '@Rule'
        if s.startswith("@") and len(s) > 1 and _RE_CALL.match(s[1:]):
            return {"type": "call", "name": s[1:]}

        # 5. 普通 token
        if _RE_TOKEN.match(s):
            return {"type": "token", "token_type": s}

        raise GrammarError(f"无效的产生式片段: {s}")

    try:
        return build_tree(production)
    except Exception as e:
        raise GrammarError(f"分析产生式失败 {production}: {str(e)}") from e


# ── 生产式还原序列化（feature 树 → production 字符串）─────────────────
# 与 analyze_production_features 对称：把展开后的树还原为 production 字符串。
# 用于 EXT inject 的结构化合并——注入不再用字符串正则/子串改 production，
# 而是 analyze → 树层合并（choice 候选插入）→ serialize 回字符串。
# 规范化输出（round-trip 语义等价）：token/call 原样，choice/seq 按成员
# 复合性加括号，repeat/optional/plus 对复合 elem 加括号。实测 466 条真实
# production 全 round-trip 等价。


def serialize_production_tree(feat: dict | None) -> str:
    """feature 树 → production 字符串（规范化，round-trip 语义等价）。

    feat 是 analyze_production_features 的产出（token/call/choice/seq/
    repeat/optional/plus）。复合成员（choice/seq）在嵌套位置自动加括号，
    保证 re-analyze 得到等价树。
    """
    if feat is None:
        return ""
    typ = feat.get("type")
    if typ == "token":
        return feat["token_type"]
    if typ == "call":
        return f"@{feat['name']}"
    if typ == "choice":
        return "|".join(_serialize_member(a) for a in feat["alternatives"])
    if typ == "seq":
        return ",".join(_serialize_member(i) for i in feat["items"])
    if typ == "repeat":
        return f"{_serialize_group(feat['elem'])}*"
    if typ == "optional":
        return f"{_serialize_group(feat['elem'])}?"
    if typ == "plus":
        return f"{_serialize_group(feat['elem'])}+"
    return ""


def _serialize_member(feat: dict | None) -> str:
    """choice/seq 的成员：复合（choice/seq）加括号，防止被外层分隔符吞并。"""
    if feat is not None and feat.get("type") in ("choice", "seq"):
        return f"({serialize_production_tree(feat)})"
    return serialize_production_tree(feat)


def _serialize_group(feat: dict | None) -> str:
    """repeat/optional/plus 的 elem：复合（choice/seq）加括号，后缀作用于整体。"""
    if feat is not None and feat.get("type") in ("choice", "seq"):
        return f"({serialize_production_tree(feat)})"
    return serialize_production_tree(feat)


# ── 树层变换（结构化注入用）─────────────────────────────────────
# 注入不再用字符串正则/子串改 production，而是 analyze → 树层合并 → serialize
# 回字符串。以下工具纯树操作，不改入参（新树），供 grammar_inject 编排。


def make_call_feature(name: str) -> dict:
    """构造语法调用 feature：{"type": "call", "name": name}。"""
    return {"type": "call", "name": name}


def insert_choice_candidate(
    feat: dict | None,
    candidate: dict,
    prepend: bool = True,
) -> dict:
    """把 candidate 作为 choice 候选并入 feat，返回新树（不改入参）。

    - feat 是 choice → 插入 alternatives（prepend 控制首/尾）
    - 否则 → 包一层新 choice（[candidate, feat] 或 [feat, candidate]）
    用于直接注入：@ExtRule 并入目标 production。
    """
    if feat is None:
        return candidate
    if feat.get("type") == "choice":
        alts = list(feat["alternatives"])
        if prepend:
            alts.insert(0, candidate)
        else:
            alts.append(candidate)
        return {"type": "choice", "alternatives": alts}
    if prepend:
        return {"type": "choice", "alternatives": [candidate, feat]}
    return {"type": "choice", "alternatives": [feat, candidate]}


_UNCHANGED = object()


def _replace_calls_rec(feat: dict | None, repl: dict) -> Any:
    """递归替换 call 节点；无变化返回哨兵 _UNCHANGED。"""
    if feat is None:
        return _UNCHANGED
    typ = feat.get("type")
    if typ == "call":
        r = repl.get(feat["name"])
        return r if r is not None else _UNCHANGED
    if typ in ("repeat", "optional", "plus"):
        ne = _replace_calls_rec(feat.get("elem"), repl)
        if ne is _UNCHANGED:
            return _UNCHANGED
        return {**feat, "elem": ne}
    if typ == "choice":
        field = "alternatives"
    elif typ == "seq":
        field = "items"
    else:
        return _UNCHANGED
    new_items = []
    changed = False
    for x in feat.get(field, []):
        nx = _replace_calls_rec(x, repl)
        if nx is _UNCHANGED:
            new_items.append(x)
        else:
            new_items.append(nx)
            changed = True
    if not changed:
        return _UNCHANGED
    return {**feat, field: new_items}


def replace_calls(feat: dict | None, repl: dict) -> dict | None:
    """递归把 call[name]（name in repl）替换为 repl[name] 的新树。

    无变化时返回原 feat（同一对象），调用方可借此判断是否 changed。
    用于传播注入：@Target → (@Ext|@Target) 全树替换。树层 name 精确匹配，
    天然避免字符串正则的整 token 边界问题（@Stmt 不误伤 @StmtOrNull）。
    """
    r = _replace_calls_rec(feat, repl)
    return feat if r is _UNCHANGED else r


if __name__ == "__main__":
    test_cases = [
        "id",
        "@Expression",
        "symbol.base.colon",
        "(@MulOp,@PrimaryExpr)*",
        "literal.number|literal.string",
        "(@VarDef|newline)*",
        "(id , symbol.base.colon , id , symbol.base.equal , @Expression)?",
        "id.keyword.if, @Expression, @Block",
        "id+",
        "(@Expr)+",
        "(id , symbol.base.colon , @Type)+",
        "literal+ | @FuncCall+",
        "(@Stmt|newline)*",
    ]

    for prod in test_cases:
        try:
            ast = analyze_production_features(prod)
            print(f"产生式: {prod}")
            print(f"AST: {ast}")
            print(_SEPARATOR)
        except Exception as e:
            print(f"失败: {prod} -> {e}")
