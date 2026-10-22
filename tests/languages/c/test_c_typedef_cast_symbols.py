"""tests/languages/c/test_c_typedef_cast_symbols.py — G4：typedef 名强转的解析期符号判定（#49）。

被测：parser 单遍「解析前符号判定」——
`parser/parser_core.py::_ScopeStack` + `_symbol_gate`/`_register_symbols`，
C 包声明面 `[Rule.parser] register` / `requires_symbol` / `[parser] symbol_namespaces`
（`grammar/c/tpc.toml`、`00_expressions.toml::CastTypedefName`），方案/判据见
`docs/gaps/gap-c-typedef-cast.md`。

判据：
  1. G4 最小矩阵（此前 check 路径失败 6 条）：函数内指针强转初值 / return / if / for /
     文件域声明 / 多层 typedef 名 —— pipeline 全部 success；
  2. 结构正确：`(T)x` ⇒ `CastExpr > CastTypedefName > TypedefName`（文本 = 原名）；
     关键字类型强转仍走 `CastTypeName`（不被新支抢）；
  3. **歧义反向**：`(a)*b`（a 变量）仍是乘法（无 CastTypedefName）；块内 `int T` 遮蔽
     后 `(T)y` 被拒；typedef 后置使用被拒；tag 名不成类型名；
  4. 作用域：块内 typedef 在块内生效；内层变量遮蔽出块后恢复外层 typedef；
  5. 门控可关性（变异判据）：去 register / 去 requires_symbol ⇒ 本文件红（见 tools 变异表）。
"""

import os

import pytest

from core.config_registry import ConfigRegistry
from core.define import iter_nodes
from pipeline import run_pipeline_on_source

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")


@pytest.fixture(scope="module")
def c_env(config_loaded):
    """C 包（含增量组件）；结束恢复 verilog（语言作用域是全局态）。"""
    del config_loaded
    ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    yield {}
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


def _nodes(ast) -> list[str]:
    return [n.node_name for n in iter_nodes(ast)] if ast is not None else []


#: G4 最小矩阵（check/pipeline 双路径都曾失败或依赖 raw 的形态）
MATRIX = {
    "函数内指针强转初值": "typedef int T;\nvoid f(void){ T *p = (T*)0; }\n",
    "return 强转": "typedef int T;\nT f(void){ return (T)x; }\n",
    "if 条件强转": "typedef int T;\nvoid f(void){ if ((T)x) y; }\n",
    "for 条件强转": "typedef int T;\nvoid f(void){ for (T i = 0; i < (T)n; i++) { } }\n",
    "文件域声明初值强转": "typedef int T;\nstatic T *gp = (T*)0;\n",
    "多层 typedef 名 + 指针": (
        "typedef struct S {\n    int x;\n} S;\nstatic S *new_item(void){ S *n = (S*)0; return n; }\n"
    ),
}


class TestG4Matrix:
    """判据 1：G4 最小矩阵全部解析成功且不含 raw 兜底。"""

    @pytest.mark.parametrize("case", list(MATRIX))
    def test_g4_case_parses(self, c_env, case):
        res = _run(MATRIX[case])
        assert res.get("success") is True and not res.get("error"), (
            case,
            res.get("error"),
        )
        assert "RawStatement" not in _nodes(res["ast"]), f"{case}: 不应依赖 raw"

    @pytest.mark.parametrize("case", list(MATRIX))
    def test_g4_case_structure_uses_symbol_branch(self, c_env, case):
        res = _run(MATRIX[case])
        names = _nodes(res["ast"])
        assert "CastTypedefName" in names, (case, names)
        assert "TypedefName" in names, (case, names)
        # 关键词类型强转支不得混入（`(T*)` 的类型名是 T，不是关键字）
        assert "CastTypeName" not in names, (case, names)


class TestStructure:
    """判据 2/3：强转结构 + 反向歧义。"""

    def test_typedef_cast_builds_cast_expr(self, c_env):
        res = _run("typedef int myint;\nvoid f(void){ x = (myint)y; }\n")
        assert res.get("success") is True, res.get("error")
        casts = [n for n in iter_nodes(res["ast"]) if n.node_name == "CastExpr"]
        assert len(casts) == 1, casts
        texts = [
            getattr(n, "content", None) or getattr(n, "value", None)
            for n in iter_nodes(casts[0])
        ]
        assert "myint" in texts, texts

    def test_keyword_cast_still_uses_keyword_branch(self, c_env):
        res = _run("void f(void){ x = (int)y; y = (char *)p; }\n")
        assert res.get("success") is True, res.get("error")
        names = _nodes(res["ast"])
        assert "CastTypeName" in names and "CastTypedefName" not in names, names

    def test_variable_paren_is_multiplication(self, c_env):
        """反例（核心）：`(a)*b`（a 变量）必须按乘法读，不得读成对 `a` 的强转。"""
        res = _run("void f(void){ int a; x = (a)*b; }\n")
        assert res.get("success") is True, res.get("error")
        names = _nodes(res["ast"])
        assert "CastTypedefName" not in names, names
        assert "CastExpr" not in names, names

    def test_pointer_qualifier_forms(self, c_env):
        res = _run(
            "typedef int T;\nvoid f(void){ x = (T*)p; y = (T **)q; z = (const T *)r; }\n"
        )
        assert res.get("success") is True, res.get("error")
        assert _nodes(res["ast"]).count("CastTypedefName") == 3, _nodes(res["ast"])


class TestScopeWall:
    """判据 3/4：作用域/声明序/遮蔽的符号事实（不是启发式）。"""

    def test_block_typedef_visible_inside_only(self, c_env):
        ok = _run("void f(void){ typedef int T; x = (T)y; }\n")
        assert ok.get("success") is True, ok.get("error")
        # 出块后 T 不再是类型名 ⇒ `(T)y` 非法
        bad = _run("void f(void){ { typedef int T; } x = (T)y; }\n")
        assert bad.get("success") is False, "块内 typedef 不得泄漏到块外"

    def test_inner_variable_shadow_restores_outer_typedef(self, c_env):
        """内层 `int T` 遮蔽只在内层生效；出块后外层 typedef 恢复 ⇒ 强转合法。"""
        res = _run("typedef int T;\nvoid f(void){ { int T; T = 1; } x = (T)y; }\n")
        assert res.get("success") is True, res.get("error")
        assert "CastTypedefName" in _nodes(res["ast"])

    def test_shadowed_typedef_name_rejected(self, c_env):
        res = _run("typedef int T;\nvoid f(void){ int T; x = (T)y; }\n")
        assert res.get("success") is False, "同名变量不得按类型名读"

    def test_parameter_name_shadows_typedef(self, c_env):
        res = _run("typedef int T;\nvoid f(int T){ x = (T)y; }\n")
        assert res.get("success") is False, "形参名不得按类型名读"

    def test_forward_typedef_use_rejected(self, c_env):
        """C 要求声明先于使用：typedef 后置 ⇒ `(T)` 不是类型名（不得向后搜符号）。"""
        res = _run("void f(void){ x = (T)y; }\ntypedef int T;\n")
        assert res.get("success") is False

    def test_tag_name_is_not_type_name(self, c_env):
        res = _run("struct t { int x; };\nvoid f(void){ x = (t)y; }\n")
        assert res.get("success") is False, "struct tag 不是 typedef 命名空间"
