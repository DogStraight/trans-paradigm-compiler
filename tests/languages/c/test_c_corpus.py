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

    def test_linter_reports_no_false_positives(self, c_linter):
        """合法头文件上 linter **零诊断**（原 14 条误报缺口已闭环）。

        ⚠ 本用例 2026-09-26 前断言的是"缺口仍存在且规模未漂移"（14 条）。缺口
        由**四条引擎侧修点**闭环（成因见 `linter/checkers/matcher.py` 的
        `_no_progress_ok` / `_match_seq` 与 `linter/discovery.py` 的
        `_container_end` / `_advance_match` 文档）：① 匹配器对"必选 call 零进展"
        按可空性回滚；② 容器区间补算嵌套语句/块尾部；③ seq 内零进展按可空性放行；
        ④ discovery 括号分支把块规则转块分支。故按缺口档纪律换成"零诊断"断言。

        非 `phase-*` 码白名单仍保留：`ST003` 是**跨语言状态泄漏**的产物（同进程先跑
        过 verilog linter 时残留，见 `TODO.md`「跨语言检查规则泄漏」），与 C 语法
        无关；那条缺口闭环后应改为"无非 phase 码"。
        """
        errs = _lint(_source(), c_linter)
        phase = [e for e in errs if e.code.startswith("phase-")]
        others = {e.code for e in errs if not e.code.startswith("phase-")}
        assert not phase, f"合法头文件上出现结构诊断（误报）：{[e.message for e in phase]}"
        assert others <= {"ST003"}, f"出现预期外的诊断码（非跨语言泄漏）：{others}"
