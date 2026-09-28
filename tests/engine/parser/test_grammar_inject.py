"""tests/parser/test_grammar_inject.py — 结构化注入测试。

inject_productions 改为 analyze → 树层合并（choice 候选插入 / call 替换）→
serialize 回字符串，替代字符串正则。覆盖：
    - 直接注入：顶层 choice 前缀 / 非 choice 包 choice / 指定索引 / 越界 append
    - 传播注入：全树替换、@TgtOrNull 不误伤、不修改 target 自身与 ext 规则
    - fail-fast（ADR-0003）：target 缺失 / 非 production 属性 → GrammarError
    - 块规则注入后 block_prods 同步（防 stale）
"""

import pytest

from core.errors import GrammarError
from core.define import GrammarRule
from parser.grammar_inject import inject_productions


def _rule(name: str, prods: list[str], **kw):
    return GrammarRule(name, production=list(prods), **kw)


class TestDirectInject:
    """直接注入：目标 production 并入 @ExtRule 候选。"""

    def test_top_level_choice_prepends_ext(self):
        rules = {"Target": _rule("Target", ["@A|@B"])}
        inject_productions(rules, {"Ext": ["@Target"]})
        assert rules["Target"].production == ("@Ext|@A|@B",)

    def test_non_choice_wraps_new_choice(self):
        rules = {"Target": _rule("Target", ["@A,@B"])}
        inject_productions(rules, {"Ext": ["@Target"]})
        # seq 是 choice 成员 → 加括号；ext 后缀（原字符串语义）
        assert rules["Target"].production == ("(@A,@B)|@Ext",)

    def test_specific_index(self):
        rules = {"Target": _rule("Target", ["@A", "@B"])}
        inject_productions(rules, {"Ext": ["@Target.production[1]"]})
        assert rules["Target"].production == ("@A", "@B|@Ext")

    def test_index_out_of_range_appends(self):
        rules = {"Target": _rule("Target", ["@A"])}
        inject_productions(rules, {"Ext": ["@Target.production[5]"]})
        assert rules["Target"].production == ("@A", "@Ext")

    def test_multiple_ext_sequential(self):
        rules = {"Target": _rule("Target", ["@A|@B"])}
        inject_productions(rules, {"Ext1": ["@Target"], "Ext2": ["@Target"]})
        assert rules["Target"].production == ("@Ext2|@Ext1|@A|@B",)

    def test_injected_result_re_parses(self):
        from parser.rule_selector import analyze_production_features

        rules = {"Target": _rule("Target", ["@A|@B"])}
        inject_productions(rules, {"Ext": ["@Target"]})
        feat = analyze_production_features(rules["Target"].production[0])
        assert feat is not None
        assert feat["type"] == "choice"
        assert [a["name"] for a in feat["alternatives"]] == ["Ext", "A", "B"]


class TestPropagateInject:
    """传播注入：引用 @Target 的其它规则全树替换。"""

    def test_call_replaced_inside_seq(self):
        rules = {
            "Target": _rule("Target", ["@A"]),
            "Other": _rule("Other", ["@X,@Target,@Y"]),
        }
        inject_productions(rules, {"Ext": ["@Target"]})
        assert rules["Other"].production == ("@X,(@Ext|@Target),@Y",)

    def test_composite_name_not_false_positive(self):
        # @TargetOrNull 的 call name 是 TargetOrNull ≠ Target，树层天然不误伤
        rules = {
            "Target": _rule("Target", ["@A"]),
            "Other": _rule("Other", ["@TargetOrNull", "@Target"]),
        }
        inject_productions(rules, {"Ext": ["@Target"]})
        # @TargetOrNull 的 call name 是 TargetOrNull ≠ Target，树层天然不误伤；
        # @Target 单独成元素 → 顶层 choice 规范序列化（无冗余括号）
        assert rules["Other"].production == ("@TargetOrNull", "@Ext|@Target")

    def test_repeat_elem_replaced(self):
        rules = {
            "Target": _rule("Target", ["@A"]),
            "Other": _rule("Other", ["@Target*"]),
        }
        inject_productions(rules, {"Ext": ["@Target"]})
        assert rules["Other"].production == ("(@Ext|@Target)*",)

    def test_self_and_ext_rules_not_propagated(self):
        rules = {
            "Target": _rule("Target", ["@A", "@X,@Target"]),
            "Ext": _rule("Ext", ["@Target"]),
            "Other": _rule("Other", ["@Target"]),
        }
        inject_productions(rules, {"Ext": ["@Target"]})
        # 第一遍直接注入改 Target.production[0]（非 choice → 后缀）
        assert rules["Target"].production == ("@A|@Ext", "@X,@Target")
        # 第二遍跳过 target 自身与 ext 规则（ext 规则未被改写，production 保持原 list）
        assert rules["Ext"].production == ["@Target"]
        assert rules["Other"].production == ("@Ext|@Target",)

    def test_multiple_targets_propagate(self):
        rules = {
            "T1": _rule("T1", ["@a"]),
            "T2": _rule("T2", ["@b"]),
            "Other": _rule("Other", ["@T1,@T2"]),
        }
        inject_productions(rules, {"Ext": ["@T1", "@T2"]})
        assert rules["Other"].production == ("(@Ext|@T1),(@Ext|@T2)",)


class TestEmptyProductionSlot:
    """**空槽位**：非块规则的空产生式是"无自有形态的扩展点位"，注入即填充它。

    两种空产生式的含义（见 `grammar/grammar_rule_fields.md` §production）：
    - 块规则（`is_block`）：形态由块机制驱动（`block_prods`），注入无处可落 → no-op；
    - 非块规则：空槽位 → 注入成为它**唯一的元素**（越界 append 的零长特例）。
    宿主通常写成 `@Slot*` / `@Slot?`，故"槽位有形态"不等于"宿主变必选"。
    """

    def test_empty_production_non_block_is_filled(self):
        rules = {"Slot": _rule("Slot", []), "Host": _rule("Host", ["@A", "@Slot*"])}
        inject_productions(rules, {"Ext": ["@Slot.production[0]"]})
        assert rules["Slot"].production == ("@Ext",)
        # 传播注入照旧：宿主的引用变成 (@Ext|@Slot)——两条路径都指到填充后的 Ext
        assert rules["Host"].production == ("@A", "(@Ext|@Slot)*")

    def test_empty_production_index_is_irrelevant(self):
        """零长 production 没有"第 N 个元素"——越界下标同样落在元素 0。"""
        rules = {"Slot": _rule("Slot", [])}
        inject_productions(rules, {"Ext": ["@Slot.production[7]"]})
        assert rules["Slot"].production == ("@Ext",)

    def test_empty_production_block_rule_stays_untouched(self):
        """块规则的空产生式由块机制驱动，注入不落进去（保持 no-op）。"""
        rules = {"Root": _rule("Root", [], is_block=True)}
        inject_productions(rules, {"Ext": ["@Root.production[0]"]})
        assert list(rules["Root"].production) == []

    def test_non_empty_production_untouched_by_this_branch(self):
        """对照：非空 production 仍走原语义（本分支只接管零长形态）。"""
        rules = {"Target": _rule("Target", ["@A"])}
        inject_productions(rules, {"Ext": ["@Target.production[0]"]})
        assert rules["Target"].production == ("@A|@Ext",)


class TestFailFast:
    """fail-fast（ADR-0003）：配置错误直接报错。"""

    def test_missing_target_raises(self):
        rules = {"A": _rule("A", ["@B"])}
        with pytest.raises(GrammarError, match="注入目标规则"):
            inject_productions(rules, {"Ext": ["@Missing"]})

    def test_non_production_attr_raises(self):
        rules = {"A": _rule("A", ["@B"])}
        with pytest.raises(GrammarError, match="仅支持 production"):
            inject_productions(rules, {"Ext": ["@A.node"]})


class TestBlockSync:
    """块规则注入后 block_prods 同步（防 stale）。"""

    def test_block_prods_resynced_after_inject(self):
        rules = {
            "Block": _rule(
                "Block",
                ["keyword.begin", "@A", "keyword.end"],
                is_block=True,
            )
        }
        inject_productions(rules, {"Ext": ["@Block.production[1]"]})
        assert rules["Block"].production == ("keyword.begin", "@A|@Ext", "keyword.end")
        assert rules["Block"].block_start == "keyword.begin"
        assert rules["Block"].block_end == "keyword.end"
        assert rules["Block"].block_prods == ["@A|@Ext"]
