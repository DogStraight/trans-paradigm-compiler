"""tests/languages/c/test_c_corpus_impl.py — C 包真实语料：**实现面**样本。

与 `ring_buffer.h`（声明面）配对：本文件拿 `samples/ring_buffer.c`（9 个函数定义 =
初始化 / 计数 / 入队 / 出队 / 重置 / 求和 / 查找 / 汇总 / 扫描，含 for·while·do-while·
switch·goto·标号、**链式后缀**、复合赋值、三目）整文件解析，断言：

1. 顶层节点构成（2 注释 + 8 Declaration + 9 FuncDef）——数量与节点名都要对；
2. **控制流结构确实进树**（switch / for / while / do-while / goto / 标号 各至少一个，
   不是"能解析就行"）；
3. 表达式面确实被用上（后缀链三类 / 二元 / 一元）；
4. linter 诊断只落在已知的 `phase-*` 码上，且数量与缺口档记录一致。

⚠ 样本写法受当前语法面约束（无初始化器 / 无链式后缀 / 无 sizeof·cast·逗号运算符 /
无预处理），理由写在样本头注里——**样本的"不自然"本身就是阶段边界的证据**。
⚠ 链式后缀（`r->items[i].key`）此前属"已知边界"，2026-09-25 支持后样本已**长回**
自然写法（`test_c_postfix.py` 是能力判据，这里是整文件回归）。
"""

import os

from core.define import iter_nodes

from tests.languages.c.conftest import _lint, _node_names, _parse

_SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "ring_buffer.c")

# 顶层构成（随样本扩容更新）：
#   3 个块注释（文件头 / "用上阶段 2b" 段 / "字符串转义" 段）
#   + 5 条类型声明（size_alias / enum / struct ring_item / typedef ring_item / struct ring）
#   + 2 条带初始化器的声明（指示符初始化 ring_marks / sizeof ring_item_size）
#   + 2 条带初始化器的声明（**含转义引号的字符串 ring_banner** / 带指示符的 ring_default）
#   + 9 个函数定义（ring_init / ring_count / ring_push / ring_pop / ring_reset /
#     ring_sum / ring_find / ring_total / ring_scan）
_TOP = (
    ["Comment"]
    + ["Declaration"] * 5
    + ["Comment"]
    + ["Declaration"] * 2
    + ["Comment"]
    + ["Declaration"] * 2
    + ["FuncDef"] * 9
)


def _source() -> str:
    with open(_SAMPLE, encoding="utf-8") as f:
        return f.read()


def _all(ast) -> list:
    return list(iter_nodes(ast))


class TestImplementationSample:
    def test_whole_file_parses(self, c):
        ast = _parse(_source(), c)
        assert _node_names(ast) == _TOP, _node_names(ast)

    def test_every_function_has_a_body(self, c):
        ast = _parse(_source(), c)
        funcs = [n for n in ast.sub_node if n.node_name == "FuncDef"]
        assert len(funcs) == 9
        for fn in funcs:
            assert fn.body.node_name == "CompoundStmt"

    def test_control_flow_constructs_are_present(self, c):
        """六种控制流形态各自出现——缺哪个都说明对应规则没接上。"""
        names = [n.node_name for n in _all(_parse(_source(), c))]
        for want in ("SwitchStmt", "ForStmt", "WhileStmt", "DoWhileStmt", "GotoStmt", "LabelStmt"):
            assert want in names, f"样本里的 {want} 没进 AST（规则可能没接上）"

    def test_labels_and_cases_are_present(self, c):
        names = [n.node_name for n in _all(_parse(_source(), c))]
        assert names.count("CaseLabel") >= 2
        assert "DefaultLabel" in names
        assert names.count("BreakStmt") >= 2

    def test_expression_forms_are_present(self, c):
        """后缀链、二元、一元各自出现（后缀三类都在本样本里：调用/下标/成员）。"""
        names = [n.node_name for n in _all(_parse(_source(), c))]
        for want in ("PostfixExpr", "CallSuffix", "IndexSuffix", "MemberSuffix", "BinaryOp", "UnaryOp"):
            assert want in names, f"样本里的 {want} 没进 AST"

    def test_function_count_matches_source(self, c):
        """函数个数与源码里的定义数一致（防"部分函数被静默吞掉"）。"""
        ast = _parse(_source(), c)
        assert len([n for n in _node_names(ast) if n == "FuncDef"]) == 9

    def test_linter_reports_no_false_positives(self, c_linter):
        """实现文件上 linter **零诊断**（原 7 条结构误报缺口已闭环）。

        ⚠ 本用例 2026-09-26 前断言的是"`phase-*` 计数 = 缺口规模"（记录 7 条）。
        缺口由四条引擎侧修点闭环（成因见 `linter/checkers/matcher.py` 的
        `_no_progress_ok` / `_match_seq` 与 `linter/discovery.py` 的
        `_container_end` / `_advance_match` 文档），故按缺口档纪律换成"零诊断"
        断言——它同时是那次修复的**回归守**。

        ⚠ 原先还留着 `ST003` 白名单（跨语言状态泄漏的产物）。**2026-09-26 该泄漏已修**
        （`_push_loaded_config` 对"本包未声明的 key"推回编译期默认——旧实现留着**上一个
        语言**推的值，于是 C 源上跑起 verilog 的排版检查），白名单随之收紧为"无任何
        非 `phase-*` 码"；跨语言的直接判据见
        `test_cross_language_no_check_rule_leak`。
        """
        errs = _lint(_source(), c_linter)
        phase = [e for e in errs if e.code.startswith("phase-")]
        assert not phase, f"合法实现文件上出现结构诊断（误报）：{[e.message for e in phase]}"
        others = {e.code for e in errs if not e.code.startswith("phase-")}
        assert not others, f"出现非结构诊断（跨语言泄漏？）：{others}"

    def test_cross_language_no_check_rule_leak(self):
        """**先跑过 verilog linter** 再扫 C 源，诊断集合与干净进程一致（= 空）。

        这条是 `TODO.md`「跨语言检查规则泄漏」给出的判据，也是那个修复的回归守：
        泄漏的机制不在 linter 自身（每次 `scan` 都新建 `CheckerRegistry`），而在
        **模块级 `declare_cfg` 变量**——C 包不声明 `linter.style_check` /
        `linter.macro_hygiene`，旧实现切语言时"什么都不推"，于是留着 verilog 的配置。
        故断言分两层：**配置层**（切到 C 后回到默认 `{}`）+ **症状层**（长行也不报 ST003）。
        """
        from core.define import GrammarRulesRegister
        from linter import scanner as sc
        from linter.scanner import LinterScanner

        verilog_plugins = os.path.join("grammar", "verilog", "plugins")
        LinterScanner(
            rules_dir="grammar/verilog",
            register=GrammarRulesRegister(),
            ext_dirs=[verilog_plugins],
        ).scan("module m();\nendmodule\n")
        assert sc._style_check_cfg.get("enabled") is True, "前置：verilog 档应启用排版检查"

        c_linter = LinterScanner(rules_dir="grammar/c", register=GrammarRulesRegister())
        assert sc._style_check_cfg == {}, "切到 C 后排版检查配置应回到默认（未声明）"
        long_line = "int x = 0; /* " + "y" * 110 + " */\n"
        assert [d.code for d in c_linter.scan(long_line)] == []
        assert _lint(_source(), c_linter) == []

