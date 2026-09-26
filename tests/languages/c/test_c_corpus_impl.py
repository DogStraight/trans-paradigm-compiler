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
#   2 个块注释（文件头 + "用上阶段 2b" 那段的说明）
#   + 5 条类型声明（size_alias / enum / struct ring_item / typedef ring_item / struct ring）
#   + 3 条带初始化器的文件级声明（指示符初始化 ring_marks / sizeof ring_item_size /
#     带指示符的 ring_default）
#   + 9 个函数定义（ring_init / ring_count / ring_push / ring_pop / ring_reset /
#     ring_sum / ring_find / ring_total / ring_scan）
_TOP = (
    ["Comment"]
    + ["Declaration"] * 5
    + ["Comment"]
    + ["Declaration"] * 3
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

    def test_linter_gap_is_recorded(self, c_linter):
        """⚠ **已知缺口**（引擎侧，见 `docs/gaps/gap-parser-linter-approximation.md`）：
        解析侧完全正常，linter 的语句发现/"语句结束"判定对 C 的声明形态误报。

        断言分两截，各自稳定：
        1. **`phase-*` 计数** = 缺口规模（与包状态绑定，变化须重记并复核文档）；
        2. **非 `phase-*` 码只允许 `ST003`** —— `ST003` 是**跨语言状态泄漏**的产物（见下），
           与 C 语法无关。

        ⚠ 跨语言泄漏（2026-09-25 实测，本轮真实语料工作发现）：同一进程里**先跑过
        verilog linter** 再切到 `grammar/c` 扫 C 源，结果会多出 1 条 `ST003`
        （verilog 的检查规则残留，C 包自身没有 `rules/`）。即**检查结果依赖测试顺序**
        ——与 `tests/README.md` 记录的"多语言同进程串味"同类，已登记 TODO。
        故此处按"`phase-*` 计数 + 非 phase 码白名单"断言，而不是断言总数。
        """
        errs = _lint(_source(), c_linter)
        phase = [e for e in errs if e.code.startswith("phase-")]
        others = {e.code for e in errs if not e.code.startswith("phase-")}
        assert phase and len(phase) == _RECORDED_PHASE_GAP, (
            f"缺口规模变了（{len(phase)} 条，记录 {_RECORDED_PHASE_GAP}）——"
            "按缺口档纪律：重新记录并同步文档，不要随手改断言"
        )
        assert others <= {"ST003"}, f"出现预期外的诊断码（非跨语言泄漏）：{others}"


# 实测记录（阶段 3 完成 + 本样本定稿时；数字与包状态绑定，变化须重记）
_RECORDED_PHASE_GAP = 7
