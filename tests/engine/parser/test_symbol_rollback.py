"""tests/engine/parser/test_symbol_rollback.py — 符号 store 的回滚语义（P3 前置）。

覆盖三处（task-18 实测出的回滚洞）：
  ① `_ScopeStack.restore(state)` 必须撤销**同深度**的 `register`（栈深度不变、
     只改当前作用域内容的注册，正是"失败候选提前注册"的形态）；
  ② `ParseContext.create_snapshot`/`restore_snapshot` 必须**连带**回滚绑定的符号
     store（`bind_symbol_store`）——调用现场与 `parser/block_parser.py` 的
     `parse_sentence` 候选循环、`parser/_production.py` 的 `_try_production` 一致：
     先拍快照 → 试候选 → 失败即 restore；
  ③ pratt 分支的作用域帧必须配对（`try_rule_productions`）：声明了 `scope` 的 pratt
     规则在 pratt 内提前注册的符号，规则退出（含失败）后不得留在符号表里。

反向自证：三处修复各自被回退时本文件必须变红（变异已登记在 `tools/check_gate_efficacy.py`，`--only` 可单独抽查）。
"""

import importlib

importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

from core.define import GrammarRule, Token  # noqa: E402
from parser.parser_core import ParseContext, Parser, _ScopeStack  # noqa: E402
from parser._production import try_rule_productions  # noqa: E402
from parser.rule_selector import RuleSelector  # noqa: E402


def _token(type_: str, content: str = "") -> Token:
    return Token(type=type_, content=content or type_, line=1, column=0)


# ── ① _ScopeStack 回滚语义 ────────────────────────────────────────────


class TestScopeStackRollback:
    def test_same_depth_register_is_rolled_back(self):
        """同深度回滚：snapshot → register（不 push）→ restore ⇒ 符号消失。"""
        s = _ScopeStack()
        snap = s.snapshot()
        s.register("leaked", "typedef")
        assert s.lookup("leaked") == "typedef"  # 注册当场可见
        s.restore(snap)
        assert s.lookup("leaked") is None, "同深度 register 未被撤销"

    def test_overwritten_value_is_restored_exactly(self):
        """精确回滚：注册前的原值被覆盖 ⇒ restore 还原原值（不是删掉）。"""
        s = _ScopeStack()
        s.register("myint", "variable")
        snap = s.snapshot()
        s.register("myint", "typedef")  # 候选误判成 typedef
        s.restore(snap)
        assert s.lookup("myint") == "variable", "回滚应还原原值而非删除"

    def test_register_in_deeper_scope_dropped_with_scope(self):
        """截栈路径：深层作用域里注册的符号随作用域一起消失。"""
        s = _ScopeStack()
        snap = s.snapshot()
        s.push("Block", "block")
        s.register("inner", "variable")
        assert s.lookup("inner") == "variable"
        s.restore(snap)
        assert s.depth == 1
        assert s.lookup("inner") is None

    def test_restore_after_pop_rolls_back_shallower_register(self):
        """边界：先 push/register、再 pop、再在浅层 register，然后回滚到更晚的快照。

        快照之后写入的日志必须按**日志长度**（而非栈深度）判定——否则浅层新注册
        会漏撤销。
        """
        s = _ScopeStack()
        depth0 = s.snapshot()
        s.push("Block", "block")
        s.register("a", "variable")
        snap_inner = s.snapshot()
        s.pop()  # 帧退出：a 随作用域消失
        s.register("b", "variable")  # 浅层新注册
        s.restore(snap_inner)  # 回到 snap_inner 时刻（当前栈比快照浅）
        assert s.lookup("b") is None, "浅层新注册未被撤销"
        assert s.lookup("a") is None
        s.restore(depth0)
        assert s.depth == 1


# ── ② ParseContext 快照连带符号 store ─────────────────────────────────


class TestParseContextSnapshot:
    def test_context_snapshot_rolls_back_bound_symbol_store(self):
        """候选循环形态：拍快照 → 注册 → 候选失败 restore ⇒ store 干净。"""
        store = _ScopeStack()
        ctx = ParseContext([_token("id", "x")])
        ctx.bind_symbol_store(store)
        snap = ctx.create_snapshot()
        # 模拟失败候选的"提前注册"
        store.register("leaked", "typedef")
        store.push("Candidate", "block")
        store.register("inner_leak", "variable")
        ctx.restore_snapshot(snap)
        assert store.lookup("leaked") is None
        assert store.lookup("inner_leak") is None
        assert store.depth == 1

    def test_unbound_context_snapshot_still_works(self):
        """未绑定 store（纯词法/单测路径）：快照仍可用，只是不含符号态。"""
        ctx = ParseContext([_token("id", "x")])
        snap = ctx.create_snapshot()
        ctx.advance_token()
        ctx.restore_snapshot(snap)
        assert ctx.token_pointer == 0

    def test_with_block_rolls_back_symbols_on_exception(self):
        """`with context:`（异常回滚路径）同样覆盖符号 store。"""
        store = _ScopeStack()
        ctx = ParseContext([_token("id", "x")])
        ctx.bind_symbol_store(store)
        try:
            with ctx:
                store.register("boom", "typedef")
                raise RuntimeError("候选内部异常")
        except RuntimeError:
            pass
        assert store.lookup("boom") is None


# ── ③ parser 每轮重建 store + pratt 作用域帧 ──────────────────────────


def _bare_parser() -> Parser:
    """最小 Parser：合成规则表（不加载任何语言包），仅用于 parse 入口的状态验证。"""
    rules = {
        "Root": GrammarRule("Root", parser={"production": ["id"]}),
    }
    stmt = [n for n, r in rules.items() if r.has_pass_end_case()]
    return Parser(
        rules=rules,
        rule_selector=RuleSelector(rules, stmt),
        log_file="",
        silent=True,
    )


class TestParserSymbolLifecycle:
    def test_symbol_store_rebuilt_per_parse(self):
        """每轮 `parse()` 重建 store：上一轮 root 作用域的残留不得被本轮读到。"""
        parser = _bare_parser()
        parser.scope_stack.register("stale", "typedef")
        assert parser.scope_stack.lookup("stale") == "typedef"
        parser.parse([_token("id", "x")])
        assert parser.scope_stack.lookup("stale") is None, "跨 parse 残留未清理"
        assert parser.scope_stack.depth == 1

    def test_pratt_rule_scope_is_popped_even_on_failure(self):
        """pratt 规则声明的 `scope` 必须配对进出：pratt 内注册的符号不留在外层。

        修复前该分支直接 return（不推作用域帧）⇒ 符号落进**外层**作用域、pratt
        构造结束后仍可查到（泄漏）；修复后符号进 pratt 自己的帧并随帧出栈。
        """
        parser = _bare_parser()
        parser.scope_stack = _ScopeStack()
        seen: dict = {}

        class _FakePrattParser:
            scope_stack = parser.scope_stack

            def _try_pratt_rule(self, context, rule):
                del context, rule
                # 模拟"pratt 内提前注册"：注册后立刻看它在哪个作用域
                self.scope_stack.register("early", "typedef")
                seen["lookup_inside"] = self.scope_stack.lookup("early")
                seen["depth_inside"] = self.scope_stack.depth
                return None  # 失败：finally 仍须弹出作用域帧

        rule = GrammarRule(
            "Expression", parser={"production": ["id"], "scope": {"kind": "expr"}}, pratt=True
        )
        ctx = ParseContext([_token("id", "x")])
        ctx.bind_symbol_store(_FakePrattParser.scope_stack)
        result = try_rule_productions(_FakePrattParser(), ctx, rule)

        assert result is None
        assert seen["lookup_inside"] == "typedef", "注册应发生在 pratt 自己的作用域里"
        assert seen["depth_inside"] == 2, seen
        assert _FakePrattParser.scope_stack.depth == 1, "pratt 作用域帧未配对出栈"
        assert _FakePrattParser.scope_stack.lookup("early") is None, "符号泄漏到外层作用域"
