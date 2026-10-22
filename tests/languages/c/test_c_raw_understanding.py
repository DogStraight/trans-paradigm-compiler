"""tests/languages/c/test_c_raw_understanding.py — P4 理解路径**管线级**判据（C 包）。

被测两段（task-34）：analyzer 段「理解」`_raw_understand.py` + transform 段「改树」
`_raw_transform.py`（`@register_plugin`）。

**2026-10-22（#49）后口径变化**：typedef 名强转的语句级消歧已由**解析期符号判定**接管
（parser `_ScopeStack` + `[Rule.parser] register/requires_symbol`，见
`docs/gaps/gap-c-typedef-cast.md`）——`x = (myint)y;` 现在**直接建成确定结构**（不再进
RawStatement）。本文件随之保留：① 直接结构的判据（原判据 1 的升级形态）；② 仍走 raw 的
形态（复合字面量 `(t){1}`）的 verbatim 权威/渲染保真；③ 负样本（遮蔽/声明序/tag）仍被拒。

判据：
  1. `typedef int myint; void f(void){ x = (myint)y; }` ⇒ 直接确定结构
     `ExprStmt > BinaryOp(=) > CastExpr > CastTypedefName`，类型名叶子文本 = `myint`；
  2. 渲染保真：显著 token 序列逐项相同 + 格式幂等；仍为 raw 的形态（复合字面量）
     `_verbatim_text` 直出权威仍在；
  3. 负样本：遮蔽/声明在后/tag 名不成类型名均被拒（结构或语法层），赋值链维持既有宽松；
  4. 诚实边界：`(t){1}` 复合字面量承载期未覆盖 ⇒ 不提升、不报错（行为不变）。
"""

import os

import pytest

from core.config_registry import ConfigRegistry
from core.define import iter_nodes
from core.token_protocol import TRIVIA_TOKEN_TYPES
from grammar.c.plugins.semantics import _raw_understand as ru
from lexer import Lexer
from pipeline import run_pipeline_on_source

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")

TARGET = "typedef int myint;\nvoid f(void) { x = (myint)y; }\n"
TARGET_TOP = "typedef int myint;\nx = (myint)y;\n"


@pytest.fixture(scope="module")
def c_env(config_loaded):
    """C 包（含增量组件）装载；结束恢复 verilog（语言作用域是全局态）。"""
    del config_loaded
    ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    lexer = Lexer(rules_dir=_RULES, ext_dirs=[_PLUGINS])
    yield {"lexer": lexer}
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _run(src: str) -> dict:
    return run_pipeline_on_source(
        source=src,
        input_path="case.c",
        out_dir=None,
        quiet=True,
        rules_dir=_RULES,
        ext_dirs=[_PLUGINS],
    )


def _raw_nodes(ast) -> list:
    """AST 里的 raw 节点（`ast=None` ⇒ 空表：analyze 停管线时无 AST）。"""
    if ast is None:
        return []
    return [n for n in iter_nodes(ast) if n.node_name == "RawStatement"]


def _significant(lexer: Lexer, text: str) -> list[tuple[str, str]]:
    """显著 token 序列（去 trivia）：判"渲染保真"的逐项口径。"""
    return [
        (t.type, t.content)
        for t in lexer.tokenize(text)
        if t.type not in TRIVIA_TOKEN_TYPES
    ]


class TestSymbolDeterminedStructure:
    """判据 1：解析期符号判定给出**直接**确定结构（#49 起不再走 raw）。"""

    @pytest.mark.parametrize("src", [TARGET, TARGET_TOP])
    def test_cast_statement_is_determined(self, c_env, src):
        res = _run(src)
        assert res.get("success") is True and not res.get("error"), res.get("error")
        ast = res["ast"]
        # 不走 raw：语句直接建树
        assert _raw_nodes(ast) == []
        casts = [n for n in iter_nodes(ast) if n.node_name == "CastExpr"]
        assert len(casts) == 1, casts
        cast = casts[0]
        assert cast.type_name.node_name == "CastTypedefName", cast.type_name.node_name
        typename = [n for n in iter_nodes(cast.type_name) if n.node_name == "TypedefName"]
        assert len(typename) == 1, typename
        texts = [
            getattr(n, "content", None) or getattr(n, "value", None)
            for n in iter_nodes(cast)
        ]
        assert "myint" in texts, texts
        assert "int" not in texts, texts
        # 结构唯一：CastExpr 只出现一次（无 raw 候选重复产出）
        assert sum(1 for n in iter_nodes(ast) if n.node_name == "CastExpr") == 1

    def test_compound_literal_is_documented_boundary(self, c_env):
        """`(t){1}`：承载期建候选失败 ⇒ 不提升、不报错（行为与本批之前一致）。"""
        res = _run("typedef int t;\nx = (t){1};\n")
        assert res.get("success") is True and not res.get("error"), res.get("error")
        raws = _raw_nodes(res["ast"])
        assert len(raws) == 1
        assert getattr(raws[0], ru.UNDERSTAND_ATTR, None) is None
        assert getattr(raws[0], "sub_node", None) in (None, [])


class TestRenderFidelity:
    """判据 2：渲染保真不回归。"""

    @pytest.mark.parametrize("src", [TARGET, TARGET_TOP])
    def test_significant_tokens_preserved_and_idempotent(self, c_env, src):
        res = _run(src)
        output = res.get("output") or ""
        lexer = c_env["lexer"]
        assert _significant(lexer, src) == _significant(lexer, output)
        assert res.get("idempotent") is True
        # 格式幂等：对输出再跑一遍，输出不变
        again = _run(output)
        assert (again.get("output") or "") == output

    def test_verbatim_authority_kept_for_still_raw_forms(self, c_env):
        """仍走 raw 的形态：`_verbatim_text` 直出权威仍在（渲染与原句一致）。"""
        res = _run("typedef int t;\nx = (t){1};\n")
        raw = _raw_nodes(res["ast"])[0]
        assert getattr(raw, "_verbatim_text") == "x = (t){1}"
        assert "x = (t){1};" in (res.get("output") or "")

    def test_trailing_comment_survives(self, c_env):
        """行尾注释在 verbatim 切片内 ⇒ 提升不影响注释输出（逐项计数一致）。"""
        src = "typedef int myint;\nvoid f(void) { x = (myint)y; } // tail\n"
        res = _run(src)
        out = res.get("output") or ""
        assert "// tail" in out, out
        # 注释是 trivia（不进显著序列），故按 token 类型逐项计数比对
        count = lambda text: sum(  # noqa: E731
            1 for t in c_env["lexer"].tokenize(text) if t.type == "comment"
        )
        assert count(out) == count(src) == 1
        assert "// tail" in [t.content for t in c_env["lexer"].tokenize(out)]


class TestNegativeCases:
    """判据 3：负样本仍被拒（不得被"理解"掉真错）。"""

    def test_shadowed_name_still_rejected_and_not_promoted(self, c_env):
        """遮蔽（块内 `int t`）⇒ 符号表查到 variable ⇒ 不按强转读 ⇒ 语句解析失败。"""
        res = _run("typedef int t;\nvoid f(void){ int t; x = (t)y; }\n")
        assert res.get("success") is False
        assert res.get("error"), res
        ast = res.get("ast")
        if ast is not None:
            for raw in _raw_nodes(ast):
                assert getattr(raw, ru.UNDERSTAND_ATTR, None) is None
                assert getattr(raw, "sub_node", None) in (None, [])

    @pytest.mark.parametrize(
        "src",
        [
            "x=(t)y; typedef int t;\n",  # 声明在后
            "struct t{}; x=(t)y;\n",  # tag 名不成类型名
        ],
    )
    def test_lint_rejected_forms_stay_rejected(self, c_env, src):
        res = _run(src)
        assert res.get("success") is False, res
        assert res.get("error"), res

    def test_assignment_chain_keeps_existing_loose_behavior(self, c_env):
        """赋值链：既有宽松**单列**——本批不新增错误（成功/失败面与之前一致）。"""
        res = _run("typedef int t;\nx = (t)y + z = 1;\n")
        assert res.get("success") is True and not res.get("error"), res.get("error")
        assert "E002" not in str(res.get("error")) and "E003" not in str(res.get("error"))
