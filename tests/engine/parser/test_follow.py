"""tests/parser/test_follow.py — FOLLOW 集推导（parser/follow.py）。

FOLLOW 从 production 结构机械推导，替代手写 end_case 作为 check_end_case
的硬性依据。覆盖推导方程的各分支：
    - seq 基本方程：FOLLOW(B) ⊇ FIRST(β)
    - repeat/plus 循环后继：下一次迭代的 FIRST
    - choice 成员传播
    - nullable 链（optional/repeat 可空 → owner FOLLOW 传播）
    - 块规则 FIRST 种子（block_start）
    - pratt 运算符注入（内置前缀不在 production 里）
    - inline 展开传播
"""

from core.define import GrammarRule
from parser.follow import compute_follows, token_in_follow


def _rules(**kwargs) -> dict[str, GrammarRule]:
    """从 {name: dict} 构造规则表（dict 值为 GrammarRule 构造参数）。"""
    return {name: GrammarRule(name, **cfg) for name, cfg in kwargs.items()}


class TestSeqEquation:
    def test_follow_of_first_elem_gets_rest_first(self):
        rules = _rules(
            A={"parser": {"production": ["@B", "kw.end"]}},
            B={"parser": {"production": ["id"]}},
        )
        follows = compute_follows(rules)
        assert "kw.end" in follows["B"]

    def test_owner_follow_propagates_through_nullable_rest(self):
        rules = _rules(
            A={"parser": {"production": ["@B", "@C?"]}},
            B={"parser": {"production": ["id"]}},
            C={"parser": {"production": ["kw.c"]}},
            R={"parser": {"production": ["@A", "kw.end"]}},
        )
        follows = compute_follows(rules)
        # C 可空 → FOLLOW(B) ⊇ FOLLOW(A) ⊇ {kw.end}
        assert "kw.end" in follows["B"]


class TestRepeatLoop:
    def test_repeat_member_gets_iteration_first(self):
        rules = _rules(
            A={"parser": {"production": ["@B", "(@B)*", "kw.end"]}},
            B={"parser": {"production": ["id", "kw.x"]}},
        )
        follows = compute_follows(rules)
        # B 的下一次迭代以 id 开头
        assert "id" in follows["B"]
        assert "kw.end" in follows["B"]

    def test_plus_member_gets_iteration_first(self):
        rules = _rules(
            A={"parser": {"production": ["@B", "(@B)+"]}},
            B={"parser": {"production": ["id"]}},
        )
        follows = compute_follows(rules)
        assert "id" in follows["B"]


class TestChoiceAndInline:
    def test_choice_members_share_owner_follow(self):
        rules = _rules(
            A={"parser": {"production": ["(@X|@Y)", "kw.end"]}},
            X={"parser": {"production": ["kw.x"]}},
            Y={"parser": {"production": ["kw.y"]}},
        )
        follows = compute_follows(rules)
        assert "kw.end" in follows["X"]
        assert "kw.end" in follows["Y"]

    def test_inline_rule_follow_spreads_to_members(self):
        rules = _rules(
            Sel={"parser": {"production": ["@X|@Y"]}, "inline": True},
            A={"parser": {"production": ["@Sel", "kw.end"]}},
            X={"parser": {"production": ["kw.x"]}},
            Y={"parser": {"production": ["kw.y"]}},
        )
        follows = compute_follows(rules)
        assert "kw.end" in follows["X"]
        assert "kw.end" in follows["Y"]


class TestNestedSeqTailPropagation:
    """嵌套序列内的尾部 call 也要拿到"同层后续兄弟"的 FIRST。

    回归背景（2026-XX，实测）：原 `_propagate_seq` 只扫规则的**顶层元素列表**，
    元素内部的尾部 call（备选支 / 括号分组 / `?` `*` `+` 后缀组）拿不到后续兄弟的
    FIRST ⇒ 该写法在匹配期被 FOLLOW 检查拒绝（加载期静默）。c4 `IndexExpr` 的
    `(lsquare,@Expression,rsquare)+` 因此有 9 个下标形态解析截断。
    修法：`_propagate_intra` 递归分派 beta（只增不减，见 follow.py 注释）。
    """

    def test_choice_alternative_seq_tail(self):
        # 备选支是一条序列：X 同支后面就是 lit.tail
        rules = _rules(
            A={"parser": {"production": ["(@X,lit.tail)|(@Y,lit.tail2)"]}},
            X={"parser": {"production": ["id"]}},
            Y={"parser": {"production": ["kw.y"]}},
        )
        follows = compute_follows(rules)
        assert "lit.tail" in follows["X"]
        assert "lit.tail2" in follows["Y"]

    def test_grouped_seq_tail(self):
        # 括号分组同样造出嵌套 seq（无后缀也如此）：X 后跟 lit.close
        rules = _rules(
            A={"parser": {"production": ["(lit.open,@X,lit.close)"]}},
            X={"parser": {"production": ["id"]}},
        )
        follows = compute_follows(rules)
        assert "lit.close" in follows["X"]
        assert "lit.open" not in follows["X"]  # 前驱兄弟不得当后继

    def test_repeat_elem_seq_tail(self):
        # `+`/`*` 组的 elem 是 seq：组内尾部 call 拿同层兄弟 + 下一次迭代 FIRST
        rules = _rules(
            A={
                "parser": {
                    "production": [
                        "@B",
                        "(bracket.l_square_bracket,@B,bracket.r_square_bracket)+",
                    ]
                }
            },
            B={"parser": {"production": ["id"]}},
        )
        follows = compute_follows(rules)
        assert "bracket.r_square_bracket" in follows["B"]
        assert "bracket.l_square_bracket" in follows["B"]  # 循环下一迭代 FIRST


class TestNestedSeqNoOverApproximation:
    """负向：互为备选的成员之间**不得**互当前继（防"递归=乱补"）。"""

    def test_alternatives_do_not_follow_each_other(self):
        rules = _rules(
            A={"parser": {"production": ["(@X|kw.y)"]}},
            X={"parser": {"production": ["id"]}},
            R={"parser": {"production": ["@A", "kw.end"]}},
        )
        follows = compute_follows(rules)
        assert "kw.end" in follows["X"]  # 备选外的后继照常进
        assert "kw.y" not in follows["X"]

    def test_alternative_call_first_not_a_tail(self):
        # (@X|@Y)：X 的后继不得含 FIRST(Y)；Y 的后继不得含 FIRST(X)
        rules = _rules(
            A={"parser": {"production": ["(@X|@Y)"]}},
            X={"parser": {"production": ["kw.x"]}},
            Y={"parser": {"production": ["kw.y"]}},
            R={"parser": {"production": ["@A", "kw.end"]}},
        )
        follows = compute_follows(rules)
        assert follows["X"] == {"kw.end"}
        assert follows["Y"] == {"kw.end"}


class TestBlockRuleFirst:
    def test_block_rule_first_is_block_start(self):
        # 块规则剥离首尾字面后 prods 为空，FIRST 必须来自 block_start——
        # 作为 beta 侧后继进入其他规则的 FOLLOW
        rules = _rules(
            Blk={"parser": {"production": ["kw.begin", "kw.end"]}, "is_block": True},
            B={"parser": {"production": ["kw.b"]}},
            A={"parser": {"production": ["@B", "@Blk"]}},
        )
        follows = compute_follows(rules)
        assert "kw.begin" in follows["B"]  # FOLLOW(B) ⊇ FIRST(Blk) = block_start


class TestPrattOperatorInjection:
    def test_pratt_rules_get_operator_family_first(self):
        rules = _rules(
            Mul={"parser": {"production": ["@Prim", "(@Op,@Prim)*"]}, "pratt": True},
            Prim={"parser": {"production": ["id"]}, "is_atom": True},
            A={"parser": {"production": ["@Prim", "(@Prim)*"]}},
        )
        follows = compute_follows(rules, operator_members=["symbol.base."])
        # Prim 是 atom → 运算符家族注入 FOLLOW
        assert token_in_follow("symbol.base.or", follows["Prim"])


class TestTokenInFollow:
    def test_family_prefix_match(self):
        f = frozenset({"symbol.base.", "id"})
        assert token_in_follow("symbol.base.or", f)
        assert token_in_follow("id", f)
        assert not token_in_follow("keyword.if", f)
        assert not token_in_follow("symbol.extend.or", f)


class TestIntegrationWithRealGrammar:
    def test_real_grammar_follows_nonempty_and_stable(self):
        from core.define import GrammarRulesRegister

        rules = GrammarRulesRegister.get_default().rules_registration()
        follows = compute_follows(rules, ["symbol.base.", "symbol.extend."])
        # 语句规则应拿到块结束符
        assert "keyword.endmodule" in follows["AssignStmt"]
        # 表达式根应拿到运算符家族
        assert token_in_follow("symbol.base.sub", follows["Expression"])
