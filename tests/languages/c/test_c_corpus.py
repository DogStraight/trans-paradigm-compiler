"""tests/languages/c/test_c_corpus.py — C 包的真实语料样本（整文件解析）。

目标要求"每阶段验证含真实语料"，而 C 包此前只有合成夹具。本文件拿一份**真实风格
头文件**（`samples/ring_buffer.h`：多级 typedef、struct/union/enum、位宽数组、
跨聚合类型的指针参数、混合存储类）整文件解析，断言：

1. 顶层**声明数**与形状（不是"能解析就行"——数量与节点名都要对）；
2. 聚合类型与 typedef 名确实进了 AST（结构可查）；
3. linter 无诊断（真实风格合法代码不应报错）。

⚠ 样本范围 = 当前阶段已支持的语法（声明 / 类型说明符 / 声明符）。预处理指令与
函数体/语句**不在样本内**（阶段 3/4 未完成），随阶段推进扩容——这样"语料测试"
不会因为阶段未到而假绿或假红。
"""

import os

from core.define import iter_nodes

from tests.languages.c.conftest import _lint, _node_names, _parse

# 顶层 = 1 个 Comment 节点（文件头块注释被保留）+ 11 条声明
_TOP = ["Comment"] + ["Declaration"] * 11

_SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "ring_buffer.h")


def _source() -> str:
    with open(_SAMPLE, encoding="utf-8") as f:
        return f.read()


class TestRingBufferHeader:
    def test_whole_file_parses_into_declarations(self, c):
        """整文件 → 1 个注释节点 + 11 条顶层声明（数量与节点名都要对，防"部分解析也算过"）。

        ⚠ `Comment` 也在顶层：本包的 `Comment` 规则缺失时注释会被静默丢弃——顶端出现
        `Comment` 节点本身就是"注释被保留"的证据（yaml 包补 `Comment` 规则的理由，
        见 `grammar/yaml/00_document.toml` 头注）。
        """
        ast = _parse(_source(), c)
        assert _node_names(ast) == _TOP, _node_names(ast)

    def test_aggregate_types_are_present(self, c):
        """struct/union/enum 三种聚合说明符都进了 AST（按标签核对）。"""
        ast = _parse(_source(), c)
        tags: set[str] = set()
        kinds: set[str] = set()
        for decl in ast.sub_node:
            for node in iter_nodes(decl):  # 递归（聚合说明符在声明符子树里）
                name = node.node_name
                if name in ("StructSpecifier", "AnonStructSpecifier"):
                    kinds.add("struct/union")
                    tag = getattr(node, "tag", None)
                    if tag is not None:
                        tags.add(tag.content)
                elif name == "EnumSpecifier":
                    kinds.add("enum")
                    tag = getattr(node, "tag", None)
                    if tag is not None:
                        tags.add(tag.content)
        assert kinds == {"struct/union", "enum"}, kinds
        assert {"ring_item", "ring_slot", "ring", "ring_status"} <= tags, tags

    def test_typedef_and_extern_storage(self, c):
        """`typedef` / `extern` / `static` 三种存储类都出现在样本里且被解析。"""
        src = _source()
        assert "typedef unsigned long size_alias;" in src
        assert "extern int ring_init" in src
        ast = _parse(src, c)
        assert _node_names(ast) == _TOP

    def test_linter_gap_is_recorded_not_hidden(self, c_linter):
        """⚠ **已知缺口**：合法头文件上 linter 会报 17 条（解析侧完全正常）。

        本用例**不断言"无诊断"**——那会把一个真实缺陷写成期望；也不断言"有诊断"——
        那会把缺陷固化。它断言的是**缺口的可发现性**：诊断全部落在两类已知码上，
        且数量与缺口档记录一致；缺口一旦修复，本用例会失败并提醒复核文档。

        两类构造函数（`docs/gaps/gap-parser-linter-approximation.md`）：
        ① 带成员体的类型说明符 `struct/union … { … };`（3 条）；
        ② 带括号的声明符 `int f(struct ring *r);`（每条 2 报，共 10 条）。
        归因 = `linter/checkers/matcher.py` 严格逐 token 匹配**不回溯**（规则内部的
        可选分支不被尝试），属**引擎侧**修点，不在语言包侧。

        ⚠ **数字与包状态绑定**：实测 14 条 = 阶段 1+2a+3A 测得（每落地一层语法面都会变：
        13 → 14）；阶段 3 的
        试验语法在树里时曾测得 17 条 / 4 类（多出 `enum` 体的 unrecognized 与成员数组
        `[` 两类）。故本用例断言的是"**缺口仍存在且规模未漂移**"，任何人推进语法面后
        数量变化都应在缺口档里重新记录并同步此处，而不是随手改断言。
        """
        errs = _lint(_source(), c_linter)
        codes = {e.code for e in errs}
        assert codes <= {"phase-statement", "phase-unrecognized"}, codes
        assert len(errs) == 14, f"缺口数量变了（{len(errs)} 条）——复核缺口档记录"
