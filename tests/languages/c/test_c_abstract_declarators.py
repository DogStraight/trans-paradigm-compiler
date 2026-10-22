"""tests/languages/c/test_c_abstract_declarators.py — 无名抽象声明符（形参原型）。

C99 §6.7.6：`parameter-declaration` 可省略 declarator——`void f(void *, size_t);` /
`int g(const char *, const char *);` 这类「只有 `*` 链（可带类型限定符）、无名字」的
形态是真实 C 头文件的高频写法（zlib `void zmemcpy(void *, void *, z_size_t);` 等）。

本包第一版 ParamDecl 只收**具体**声明符（`@Declarator` / `@TypedefDeclarator`）⇒ 这类原型
整条不可解析（真实语料 zlib 原型声明命中，`docs/gaps/gap-c-real-corpus.md` G3；循环 #45 收口）。
修法 = ParamDecl 声明符位增加两支**抽象**形态：`@Pointer`（`*` 链 + 限定符）与
`@TypedefAbstractDeclarator`（`@TypedefName @Pointer`，接 `const T *`）；具体声明符两支
仍在最前（既有形态逐字不变）。

## 判据

- **目标形态**：解析完整（`_parse_truncated is False`）+ linter 0 + 渲染显著 token 序列
  逐项相同 + 幂等；含「限定符在前 + typedef 名 + 无名字指针」`const T *`。
- **既有形态零回归**：具名形参（`int *p` / `const char *s`）、无名字的纯类型形参（`int`）
  行为不变；具名形参照常进符号表，无名形参**不得**产生符号记录。
- **已登记边界**：函数指针/数组型抽象声明符（`int (*)(void)` / `int []`）暂不收——它们
  是**完整抽象声明符文法**（括号型）的另一档，按真实语料触发再扩；本文件锁定"仍被拒"。
- Doc: `docs/gaps/gap-c-real-corpus.md`（G3）、`grammar/c/01_declarations.toml`（ParamDecl 头注）
"""

import pytest

from core.define import iter_nodes
from core.token_protocol import TRIVIA_TOKEN_TYPES
from renderer import Renderer
from transform.normalizer import normalize_ast

from tests.languages.c.conftest import _lint, _parse

_RULES = "grammar/c"


def _render_env(c) -> Renderer:
    return Renderer(
        rules_dir=_RULES,
        line_comment_starts=c["lexer"].line_terminating_comment_starts(),
    )


def _tokens(lexer, text: str) -> list[tuple[str, str]]:
    return [
        (t.type, t.content)
        for t in lexer.tokenize(text)
        if t.type not in TRIVIA_TOKEN_TYPES
    ]


def _assert_accepted_and_faithful(c, c_linter, src: str, label: str) -> None:
    ast = _parse(src, c)
    assert ast is not None and getattr(ast, "sub_node", None), f"{label}: 空 AST"
    assert getattr(c["parser"], "_parse_truncated", None) is False, (
        f"{label}: 解析被截断（无名抽象声明符仍无产生式可匹配）"
    )
    assert _lint(src, c_linter) == [], f"{label}: linter 有诊断"
    renderer = _render_env(c)
    out = renderer.render(normalize_ast(ast))
    assert _tokens(c["lexer"], out) == _tokens(c["lexer"], src), f"{label}: {src!r} → {out!r}"
    again = _parse(out, c)
    assert renderer.render(normalize_ast(again)) == out, f"{label}: 渲染不幂等"


# (标签, 源码, 形参声明符位期望的节点名)
_CASES = [
    ("zlib 原型三参", "void zmemcpy(void *, void *, z_size_t);\n", "Pointer"),
    ("两个 const 字符串指针", "int g(const char *, const char *);\n", "Pointer"),
    ("二级指针", "void h(char **);\n", "Pointer"),
    ("const 限定指针", "void k(int * const);\n", "Pointer"),
    ("typedef 名 + 限定符 + 指针", "typedef int T;\nvoid m(const T *);\n",
     "TypedefAbstractDeclarator"),
]


class TestUnnamedAbstractPointerParams:
    """G3：无名抽象指针形参（原型声明）解析完整 + 渲染保真。"""

    @pytest.mark.parametrize("label,src,node", _CASES, ids=[c[0] for c in _CASES])
    def test_accepted_and_faithful(self, c, c_linter, label, src, node):
        _assert_accepted_and_faithful(c, c_linter, src, label)
        ast = normalize_ast(_parse(src, c))
        params = [n for n in iter_nodes(ast) if n.node_name == "ParamDecl"]
        assert params, f"{label}: 缺 ParamDecl"
        declarators = [
            getattr(p, "declarator", None) for p in params if getattr(p, "declarator", None)
        ]
        assert any(
            getattr(d, "node_name", None) == node for d in declarators
        ), f"{label}: 形参声明符节点不是 {node}（{[getattr(d, 'node_name', d) for d in declarators]}）"

    def test_unnamed_params_do_not_enter_symbol_table(self, c):
        """无名形参不得产生符号记录（`declarator` 无声明名路径 ⇒ 收集为空）。"""
        from analyzer.traversal import AnalysisTraversal

        src = "void f(void *);\nint g(const char *, int);\n"
        at = AnalysisTraversal(c["rules"], rules_dir=_RULES)
        at.analyze(normalize_ast(_parse(src, c)))
        names = {s.name for s in at.all_symbols}
        assert names == {"f", "g"}, names
        assert [str(d) for d in at.diagnostics] == []

    def test_named_params_still_collected(self, c):
        """具名形参照常进符号表（`int *p` / `const char *s` 的声明符位仍是具体声明符）。"""
        from analyzer.traversal import AnalysisTraversal

        src = "void f(int *p, const char *s);\n"
        at = AnalysisTraversal(c["rules"], rules_dir=_RULES)
        at.analyze(normalize_ast(_parse(src, c)))
        kinds = {(s.name, s.kind) for s in at.all_symbols}
        assert ("p", "variable") in kinds, kinds
        assert ("s", "variable") in kinds, kinds


class TestNamedAndPlainParamsRegression:
    """回归守卫：既有形参形态仍走前两支（AST/符号/渲染逐字不变）。"""

    @pytest.mark.parametrize(
        "src",
        [
            "void f(int *p, const char *s);\n",
            "void f(void);\n",
            "void f(int);\n",
            "void f(int a[10]);\n",
            "void f(int (*fp)(int));\n",
        ],
    )
    def test_existing_forms_unchanged(self, c, c_linter, src):
        _assert_accepted_and_faithful(c, c_linter, src, src.strip())

    def test_abstract_param_does_not_steal_named_param(self, c):
        """`void f(int *p)` 的 `p` 仍是声明名（抽象分支不是先到先得）。"""
        ast = normalize_ast(_parse("void f(int *p);\n", c))
        params = [n for n in iter_nodes(ast) if n.node_name == "ParamDecl"]
        assert len(params) == 1
        declarator = getattr(params[0], "declarator", None)
        assert getattr(declarator, "node_name", None) == "Declarator", (
            f"具名形参被读成抽象声明符：{getattr(declarator, 'node_name', declarator)}"
        )


class TestKnownAbstractDeclaratorBoundaries:
    """已登记边界：括号型抽象声明符（函数指针/数组）暂不收（完整抽象声明符文法另一档）。

    触发条件 = 真实语料出现该形态；届时扩 `@Pointer`→完整抽象声明符。本类锁"当前仍被拒"，
    防止静默把坏输入吞成 raw/截断软成功。
    """

    @pytest.mark.parametrize(
        "src",
        ["void v(int (*)(void));\n", "void w(int []);\n", "void x(int (*)[3]);\n"],
    )
    def test_boundary_still_rejected(self, c, c_linter, src):
        _parse(src, c)
        assert getattr(c["parser"], "_parse_truncated", None) is True, (
            f"{src!r}: 预期仍被拒（边界收窄后须同步更新本条）"
        )
        assert _lint(src, c_linter), f"{src!r}: 预期 linter 报错"
