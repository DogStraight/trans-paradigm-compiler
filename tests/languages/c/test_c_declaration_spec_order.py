"""tests/languages/c/test_c_declaration_spec_order.py — 声明说明符顺序自由 + 指针限定符。

C 的 `declaration-specifiers` 顺序自由：typedef 名可出现在**存储类/限定符之后**
（`extern size_t n;`、`const T *p`）。本包第一版把 typedef 名只放在首个说明符位
（`@SpecRest*` 是贪婪重复、不能含 `@TypedefName`——否则 `int x;` 的 `x` 会被当类型名吃掉），
于是这类合法代码整条无产生式可匹配（真实 C 语料 zlib/cJSON 命中，循环 #44 修）。

## 实现口径（为什么是「声明符优先」交替）

宿主规则的声明符位写成 `(@DeclaratorList|@TypedefDeclarators)?` 一类的交替：
1. 先按 `@DeclaratorList` 读（**既有形态走这支，AST/渲染逐字不变**；贪婪问题不存在）；
2. 失败再读「一个 `@TypedefName` + 声明符」，即 `TypedefDeclarators` / `TypedefDeclarator` /
   `TypedefInitDeclarator` 三个包装规则（节点绑定**仿照**被包装规则的消费面：
   `items` / `declarator`，使 `declarators.items` / `declarator.direct.head.content`
   对两种包装走同一路径）。
无需符号表、不改既有 FIRST/候选注册；`_Atomic(int) x;` 这类「限定符本身就是类型」的
形态因**第一支已经成功**而不受第二支影响。

指针限定符（C99 §6.7.6 `pointer: * type-qualifier-list_opt pointer_opt`）：`@Pointer`
加 `@TypeQualifier*`（`int * const q;` / `const char * const s`，同理真实语料命中）。

## 判据（缺陷态各自会红）

- **新形态**：解析完整（`parser._parse_truncated is False`）+ linter 0 诊断 + 渲染显著
  token 序列逐项相同 + 幂等；六个宿主各一条（Declaration / FuncDef / StructMember /
  ParamDecl / ForInitDecl / TypeName）。
- **不误吃声明符名**：`int x;` 等普通声明仍走第一支（AST 里没有包装节点、
  `declarators.items[0].declarator.direct.head.content == "x"`）。
- **符号收集路径不破**：`AnalysisTraversal` 下新形态的声明名照常进符号表。
- Doc: `docs/gaps/gap-c-real-corpus.md`（缺口 G1/G2 收口）、`grammar/c/01_declarations.toml` 头注
"""

import os

import pytest

from core.define import iter_nodes
from core.token_protocol import TRIVIA_TOKEN_TYPES
from renderer import Renderer
from transform.normalizer import normalize_ast

from tests.languages.c.conftest import _lint, _parse

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")


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
    """新形态三判据：解析完整 + linter 0 + 渲染 token 相同且幂等。"""
    ast = _parse(src, c)
    assert ast is not None and getattr(ast, "sub_node", None), f"{label}: 空 AST"
    assert getattr(c["parser"], "_parse_truncated", None) is False, (
        f"{label}: 解析被截断（该形态仍无产生式可完整匹配）"
    )
    assert _lint(src, c_linter) == [], f"{label}: linter 有诊断"
    renderer = _render_env(c)
    out = renderer.render(normalize_ast(ast))
    assert _tokens(c["lexer"], out) == _tokens(c["lexer"], src), f"{label}: {src!r} → {out!r}"
    again = _parse(out, c)
    assert renderer.render(normalize_ast(again)) == out, f"{label}: 渲染不幂等"


# (标签, 源码, 期望出现在 AST 里的包装节点)
_TYPEDEF_AFTER_SPEC = [
    ("文件作用域 extern + typedef 指针", "typedef int T;\nextern T *p;\n",
     "TypedefDeclarators"),
    ("static + typedef 值", "typedef int T;\nstatic T v;\n", "TypedefDeclarators"),
    ("块内 const + typedef 指针", "typedef int T;\nvoid h(void) { const T *p; (void)p; }\n",
     "TypedefDeclarators"),
    ("struct 成员 const + typedef 指针", "typedef int T;\nstruct S { const T *p; };\n",
     "TypedefDeclarators"),
    ("形参 const + typedef 指针", "typedef int T;\nvoid f(const T *p);\n",
     "TypedefDeclarator"),
    ("函数定义 extern + typedef 返回类型",
     "typedef int T;\nextern T f(void) { return 0; }\n", "TypedefDeclarator"),
    ("for 初值 const + typedef 指针",
     "typedef int T;\nvoid g(void) { for (const T *p = 0; p; p = 0) { } }\n",
     "TypedefInitDeclarator"),
]


class TestTypedefNameAfterSpecifiers:
    """G1：typedef 名出现在存储类/限定符之后（六个宿主）。"""

    @pytest.mark.parametrize(
        "label,src,wrapper",
        _TYPEDEF_AFTER_SPEC,
        ids=[c[0] for c in _TYPEDEF_AFTER_SPEC],
    )
    def test_accepted_and_faithful(self, c, c_linter, label, src, wrapper):
        _assert_accepted_and_faithful(c, c_linter, src, label)
        names = {n.node_name for n in iter_nodes(normalize_ast(_parse(src, c)))}
        assert wrapper in names, f"{label}: 缺 {wrapper}（{sorted(names)}）"

    def test_typename_type_slot(self, c, c_linter):
        """TypeName（`sizeof` 类型名位）同样收「限定符 + typedef 名」：`sizeof(const T *)`。"""
        src = "typedef int T;\nint n = sizeof(const T *);\n"
        _assert_accepted_and_faithful(c, c_linter, src, "sizeof 类型名位")
        type_names = [
            n for n in iter_nodes(normalize_ast(_parse(src, c))) if n.node_name == "TypeName"
        ]
        assert type_names, "缺 TypeName 节点"
        assert getattr(type_names[0], "typedef_spec", None) is not None, (
            "TypeName.typedef_spec 未绑定（`sizeof(const T *)` 的 T 会渲染丢失）"
        )

    def test_typedef_type_with_id_declarator_not_eaten(self, c, c_linter):
        """`extern T v;`：T 是类型、v 是声明名（第二支只看首 token 是 id，不吞后续声明符）。"""
        src = "typedef int T;\nextern T v;\n"
        _assert_accepted_and_faithful(c, c_linter, src, "extern T v")
        decl = normalize_ast(_parse(src, c)).sub_node[1]
        assert decl.declarators.items[0].declarator.direct.head.content == "v", (
            "声明名被误读成类型名或反之"
        )


# (标签, 源码) —— 指针限定符 C99 §6.7.6
_POINTER_QUALIFIERS = [
    ("const 指针变量", "int * const q;\n"),
    ("const 字符串指针", 'const char * const s = "x";\n'),
    ("二级指针 const", "char ** const r;\n"),
    ("形参 const 指针", "int f(int * const p);\n"),
    ("const 指针 + 双 const 形参（cJSON 形态）",
     "typedef struct S S;\nint g(const S * const p);\n"),
]


class TestPointerTypeQualifiers:
    """G2：`*` 后的类型限定符列表（`T * const p`）。"""

    @pytest.mark.parametrize(
        "label,src", _POINTER_QUALIFIERS, ids=[c[0] for c in _POINTER_QUALIFIERS]
    )
    def test_accepted_and_faithful(self, c, c_linter, label, src):
        _assert_accepted_and_faithful(c, c_linter, src, label)

    def test_pointer_quals_binding(self, c):
        """`Pointer.quals` 绑定到限定符（单值或列表；渲染 `* const p` 的空格来自它，不是硬编码）。"""
        src = "typedef int T;\nextern T * const p;\n"
        ast = normalize_ast(_parse(src, c))
        pointers = [n for n in iter_nodes(ast) if n.node_name == "Pointer"]
        assert pointers, "缺 Pointer 节点"
        quals = getattr(pointers[0], "quals", None)
        assert quals, "Pointer.quals 未绑定"
        items = quals if isinstance(quals, list) else [quals]
        names = [
            getattr(q, "node_name", None) or getattr(q, "base", None) for q in items
        ]
        assert "TypeQualifier" in names, names

    def test_unqualified_pointer_render_unchanged(self, c):
        """无限定符时 `*p` 不多出空格（渲染回归守卫：`int *p;` → `int *p;`）。"""
        src = "int *p;\n"
        ast = normalize_ast(_parse(src, c))
        out = _render_env(c).render(ast)
        assert out == "int *p;", out


# 普通声明（既有形态）回归守卫：必须仍走第一支（无包装节点、AST 路径不变）
_ORDINARY = [
    ("单声明符", "int x;\n", "x"),
    ("多词说明符", "unsigned long x;\n", "x"),
    ("多声明符", "int a, b;\n", "a"),
    ("typedef 名作首说明符", "typedef int T;\nT v;\n", "v"),
    ("函数指针", "int (*fp)(int);\n", "fp"),
    ("数组", "int a[4];\n", "a"),
    ("位域", "struct B { unsigned int f : 3; };\n", "f"),
]


class TestOrdinaryDeclarationsRegression:
    """回归守卫：普通声明仍走 `@DeclaratorList` 第一支（AST 形状/声明名不变）。

    破坏它会红：例如把交替顺序反过来（typedef 名优先）⇒ `int x;` 会把 `x` 当类型名、
    `declarators.items[0]` 路径取不到声明名。
    """

    @pytest.mark.parametrize("label,src,name", _ORDINARY, ids=[c[0] for c in _ORDINARY])
    def test_ordinary_declaration_ast_unchanged(self, c, label, src, name):
        ast = normalize_ast(_parse(src, c))
        names = {n.node_name for n in iter_nodes(ast)}
        assert not ({"TypedefDeclarators", "TypedefDeclarator"} & names), f"{label}: 误入包装分支"
        contents = {
            n.content for n in iter_nodes(ast)
            if n.node_name == "Identifier" and getattr(n, "content", None)
        }
        assert name in contents, f"{label}: 声明名 {name!r} 不在 AST（{sorted(contents)}）"


class TestWrapperSingleTraversal:
    """包装节点不得共绑同一子树：`TypedefDeclarator` 曾用 `direct = "$2.direct"` 透出
    声明符子树，导致 `iter_children` 走两遍 → 重复符号记录 + TAG001 假阳性
    （循环 #44 对抗审计实测）。修法 = 只绑 `declarator`，消费面声明候选路径
    （`FuncDef` / `ParamDecl` 的 `name_path` 列表）。"""

    def test_single_symbol_record_for_nested_declarator(self, c):
        from collections import Counter

        from analyzer.traversal import AnalysisTraversal

        src = "typedef int T;\nvoid f(const T (*cb)(struct S { int x; } *q));\n"
        at = AnalysisTraversal(c["rules"], rules_dir=_RULES)
        at.analyze(normalize_ast(_parse(src, c)))
        assert [str(d) for d in at.diagnostics] == [], "包装节点重复遍历触发假阳性诊断"
        counts = Counter((s.name, s.kind) for s in at.all_symbols)
        assert counts[("q", "variable")] == 1, counts
        assert counts[("S", "tag")] == 1, counts
        assert counts[("f", "function")] == 1, counts

    def test_single_symbol_record_for_funcdef_param(self, c):
        from collections import Counter

        from analyzer.traversal import AnalysisTraversal

        src = "typedef int T;\nextern T f(int x) { return x; }\n"
        at = AnalysisTraversal(c["rules"], rules_dir=_RULES)
        at.analyze(normalize_ast(_parse(src, c)))
        counts = Counter((s.name, s.kind) for s in at.all_symbols)
        assert counts[("x", "variable")] == 1, counts
        assert counts[("f", "function")] == 1, counts


class TestKnownOverAcceptanceBoundaries:
    """已登记的**过接受**边界（宽进口径的代价；触发条件见 gap 档）。

    交替第二支只按 token 形态判断「id 是 typedef 名」、没有符号表，于是
    `int a b;`（漏逗号）会被读成「类型 a + 声明 b」；`unsigned T x;`（两个类型
    说明符）与 `sizeof(int T)` 同理。⚠ 这确实让 linter 失去"声明符间漏逗号"的检出
    （旧行为：parse 截断 + `expected ';'`），宽进口径下**接受并登记**，不是修复目标；
    真实语料出现该形态的误报再升级（需符号表，属切片 1b）。"""

    @pytest.mark.parametrize(
        "src",
        ["int a b;\n", "int x y;\n", "typedef int T;\nunsigned T x;\n",
         "typedef int T;\nint n = sizeof(int T);\n"],
    )
    def test_boundary_still_accepted(self, c, c_linter, src):
        ast = _parse(src, c)
        assert ast is not None and getattr(ast, "sub_node", None), f"过接受边界消失：{src!r}"
        assert getattr(c["parser"], "_parse_truncated", None) is False, src
        assert _lint(src, c_linter) == [], f"{src!r}: 预期 0 诊断（登记边界）"


class TestSymbolCollectionUnchanged:
    """符号收集路径不破：新形态的声明名照常进符号表（`declarators.items` 路径统一）。"""

    def test_symbols_from_new_forms(self, c):
        """包装节点的声明名照常进符号表（函数位 / 形参位 / 文件位）。

        ⚠ 成员名不进符号表是既有口径（`StructMember` 无 `c_symbol_collect`），
        不在本条断言范围。
        """
        from analyzer.traversal import AnalysisTraversal

        src = (
            "typedef int T;\n"
            "struct R { const T *member; };\n"
            "void f(const T *param);\n"
            "extern T *global;\n"
            "extern T func(void) { return 0; }\n"
        )
        ast = normalize_ast(_parse(src, c))
        at = AnalysisTraversal(c["rules"], rules_dir=_RULES)
        at.analyze(ast)
        kinds = {
            (s.name, s.kind) for s in at.all_symbols if s.name in
            {"T", "R", "f", "param", "global", "func"}
        }
        assert ("T", "typedef") in kinds, kinds
        assert ("R", "tag") in kinds, kinds
        assert ("f", "function") in kinds, kinds
        assert ("param", "variable") in kinds, kinds
        assert ("global", "variable") in kinds, kinds
        assert ("func", "function") in kinds, kinds
