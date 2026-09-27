"""tests/languages/c/test_c23_increment_plugin.py — c23 插件的语法增量验证。

覆盖（2026-09-26 批次）：`nullptr` / `true`·`false`（表达式原子）、`bool` / `typeof`·
`typeof_unqual`（类型说明符）、`constexpr`（存储类说明符），以及**小写拼写族**
（`static_assert` 文件 + 块两作用域、`alignas` / `alignof` / `thread_local`——与 c11 的
`_` 版同构造异拼写，约定 = c23 侧各写一条同形规则，见 `16_alignas_alias.toml` 头注）。
每项都靠**声明的注入**落在核心基线的一个既有交替上——本文件同时是这些注入点的回归守。

⚠ **历史更正**：c23 插件 tpc.toml 原写"typeof / constexpr / nullptr 这类要往既有规则
交替里塞分支的增量做不了，因为现役 `grammar_inject` 只能做字符串子串补丁（且软失败）"。
实测作废：现役 `inject_productions` 的直接注入是树层 `insert_choice_candidate`，
fail-fast；缺的只是插件没写那几行声明。

⚠ 两条**形态**教训（本轮踩到并 fail-fast 拦下，写在这里防重踩）：
1. `production` 是**一条产生式的元素序列**（列表长度 = slot 数、`$N` 按元素下标），
   不是"多条备选产生式"——备选要在**同一个元素内**用 `|` 表达；
2. 裸交替与逗号同现时 `|` **先结合**：`"kw.a|kw.b, X"` = `choice[kw.a, (kw.b, X)]`，
   不是 `(kw.a|kw.b), X`。要"两种拼写之一 + 后续元素"就只让**首元素**承担交替。
"""

import os
import tomllib
from pathlib import Path

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister, iter_nodes
from core.token_protocol import TRIVIA_TOKEN_TYPES
from lexer import Lexer
from linter.scanner import LinterScanner
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from renderer import Renderer

ROOT_DIR = Path(__file__).resolve().parents[3]
_PACK = "grammar/c"
_PLUGINS = os.path.join(_PACK, "plugins")

# (标签, 源码, 期望出现的新节点)  —— 全部要求：进 AST + 渲染逐字还原 + 幂等 + linter 零诊断
_CASES = [
    ("nullptr 初始化", "int *p = nullptr;\n", "NullptrLiteral"),
    ("nullptr 参与比较", "int q = (p == nullptr);\n", "NullptrLiteral"),
    ("true / false", "int b = true;\nint c = false;\n", "BoolLiteral"),
    ("bool 声明", "bool flag;\n", "BoolType"),
    ("bool 与限定符/字面量", "const bool on = true;\n", "BoolType"),
    ("bool 参数类型", "void f(bool x);\n", "BoolType"),
    ("bool 结构成员", "struct s { bool ok; };\n", "BoolType"),
    ("typeof 表达式形态", "int x;\ntypeof(x) y;\n", "TypeofSpec"),
    ("typeof 类型名形态", "typeof(int) z;\n", "TypeofSpec"),
    ("typeof 指针类型名", "typeof(char *) p2;\n", "TypeofSpec"),
    ("typeof_unqual", "typeof_unqual(int) w;\n", "TypeofSpec"),
    ("constexpr 对象", "constexpr int n = 4;\n", "ConstexprSpec"),
    ("constexpr 与 static", "static constexpr int m = 5;\n", "ConstexprSpec"),
    # 小写拼写（C23 关键字化）—— 约定 = "c23 侧各写一条同形规则"，见 16_alignas_alias.toml
    ("static_assert 文件作用域", 'static_assert(1, "x");\n', "StaticAssertC23Decl"),
    ("static_assert 块作用域", 'void f(void) {\n    static_assert(1, "x");\n}\n',
     "StaticAssertC23Decl"),
    ("static_assert 在 if body", 'void f(int a) {\n    if (a)\n        static_assert(1, "x");\n}\n',
     "StaticAssertC23Decl"),
    ("alignas 常量表达式", "alignas(16) char buf[64];\n", "AlignasC23Spec"),
    ("alignas 说明符序列其余位", "int alignas(8) x;\n", "AlignasC23Spec"),
    ("alignas 类型名形态", "alignas(double) char c;\n", "AlignasC23TypeSpec"),
    ("alignas 块作用域", "void f(void) {\n    alignas(16) int x;\n}\n", "AlignasC23Spec"),
    ("alignas 结构成员", "struct s2 {\n    alignas(8) int x;\n};\n", "AlignasC23Spec"),
    ("alignof 表达式", "int a2 = alignof(int);\n", "AlignofC23Expr"),
    ("alignof 参与二元运算", "int b2 = alignof(int) * 2;\n", "AlignofC23Expr"),
    ("thread_local", "thread_local int tls;\n", "ThreadLocalC23Spec"),
    ("thread_local 与 static", "static thread_local int tls2;\n", "ThreadLocalC23Spec"),
    # c23 类型词：位精确整型与十进制浮点（注入 `SimpleType`，与 bool 同宿主）
    ("_BitInt(8)", "_BitInt(8) a;\n", "BitIntSpec"),
    ("_BitInt(64)", "_BitInt(64) b;\n", "BitIntSpec"),
    ("_BitInt 宽度是表达式（语法层宽进）", "_BitInt(N) c;\n", "BitIntSpec"),
    ("_BitInt 结构成员", "struct s3 {\n    _BitInt(8) x;\n};\n", "BitIntSpec"),
    ("_BitInt 参数位", "void f(_BitInt(8) x);\n", "BitIntSpec"),
    ("_BitInt 类型名位（sizeof）", "int n3 = sizeof(_BitInt(8));\n", "BitIntSpec"),
    ("_Decimal32", "_Decimal32 a;\n", "DecimalSpec"),
    ("_Decimal64", "_Decimal64 b;\n", "DecimalSpec"),
    ("_Decimal128", "_Decimal128 c;\n", "DecimalSpec"),
    ("_Decimal 结构成员", "struct s4 {\n    _Decimal64 x;\n};\n", "DecimalSpec"),
    ("_Decimal 参数位", "void f(_Decimal32 x);\n", "DecimalSpec"),
    ("_Decimal 类型名位（sizeof）", "int n4 = sizeof(_Decimal128);\n", "DecimalSpec"),
]


def _env() -> dict:
    ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS)
    rules = setup_grammar(_PACK, GrammarRulesRegister(), ext_dirs=[_PLUGINS])
    stmt = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=_PACK, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
    )
    lexer = Lexer(rules_dir=_PACK, ext_dirs=[_PLUGINS])

    def parse(src: str):
        return parser.parse(lexer.tokenize(src))

    def render(src: str) -> str:
        ast = parse(src)
        assert ast is not None, f"解析不出 AST：{src!r}"
        return Renderer(rules_dir=_PACK).render(ast)

    return {
        "rules": rules,
        "parse": parse,
        "render": render,
        "tokens": lambda text: [
            (t.type, t.content)
            for t in lexer.tokenize(text)
            if t.type not in TRIVIA_TOKEN_TYPES
        ],
        "lint": lambda src: LinterScanner(
            rules_dir=_PACK, register=GrammarRulesRegister(), ext_dirs=[_PLUGINS]
        ).scan(src),
    }


@pytest.fixture
def restore_language():
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _ids() -> list[str]:
    return [c[0] for c in _CASES]


class TestC23Increments:
    @pytest.mark.parametrize("label,src,node", _CASES, ids=_ids())
    def test_parses_into_expected_node(self, restore_language, label, src, node):
        ast = _env()["parse"](src)
        assert ast is not None
        names = {n.node_name for n in iter_nodes(ast)}
        assert node in names, f"{label}: 期望 {node}，实得 {sorted(names)}"

    @pytest.mark.parametrize("label,src,node", _CASES, ids=_ids())
    def test_render_faithful_and_idempotent(self, restore_language, label, src, node):
        """判据 = **显著 token 序列逐项相同** + 幂等（本包保真度的既有口径）。

        不逐字比对：块体（`struct { … }`）由布局决定换行，`char *` 在类型名位置
        渲染成 `char*`（**核心基线既有行为**，实测 `sizeof(char *)` / `(char *)q`
        同样如此——见 `docs/gaps/gap-language-pack-scope.md` 渲染现状表）。
        C 空白无关 ⇒ token 序列相同即内容不丢、语义不变。
        """
        del label, node
        env = _env()
        out = env["render"](src)
        assert env["tokens"](out) == env["tokens"](src), f"{src!r} → {out!r}"
        assert env["render"](out) == out, "不幂等"

    @pytest.mark.parametrize("label,src,node", _CASES, ids=_ids())
    def test_lints_clean(self, restore_language, label, src, node):
        del label, node
        assert _env()["lint"](src) == []


class TestC23InjectionPoints:
    """注入点必须是"最窄的那个"——一次注入覆盖所有位点。"""

    def test_bool_and_typeof_go_through_simple_type(self, restore_language):
        """`bool` / `typeof` 注进 `SimpleType`（内建类型词）⇒ 声明/成员/参数/类型名四处生效。"""
        rules = _env()["rules"]
        simple = " ".join(str(p) for p in rules["SimpleType"].production)
        for name in ("BoolType", "TypeofSpec"):
            assert f"@{name}" in simple, f"SimpleType 缺 @{name}：{simple}"

    def test_atom_increments_reach_both_atom_lists(self, restore_language):
        rules = _env()["rules"]
        for name in ("NullptrLiteral", "BoolLiteral"):
            for host in ("PrimaryExpr", "PostfixExpr"):
                joined = " ".join(str(p) for p in rules[host].production)
                assert f"@{name}" in joined, f"{host} 的原子清单缺 @{name}：{joined}"

    def test_constexpr_goes_through_storage_class(self, restore_language):
        rules = _env()["rules"]
        store = " ".join(str(p) for p in rules["StorageClass"].production)
        assert "@ConstexprSpec" in store, store

    def test_type_words_go_through_simple_type(self, restore_language):
        """`_BitInt` / `_Decimal*` 与 `bool`/`typeof` 同宿主 `SimpleType`（最窄公共点）。

        `SimpleType` 被 `TypeSpecifier`（声明 / 类型名首说明符）、`SpecRest`、`MemberSpec`
        （结构成员）、`ParamSpec`（参数）、`CastTypeName`（强制转换）共同引用 ⇒ 一次注入
        多处生效。⚠ 对照 `c11/15_alignas.toml` 的 A/B：那里没有公共宿主，只能逐点铺，
        而且逐点铺还会踩到可达性/布局的坑——**能挑公共宿主就别逐点**。
        """
        rules = _env()["rules"]
        simple = " ".join(str(p) for p in rules["SimpleType"].production)
        for name in ("BitIntSpec", "DecimalSpec"):
            assert f"@{name}" in simple, f"SimpleType 缺 @{name}：{simple}"

    def test_decimal_literal_suffix_is_a_known_gap(self, restore_language):
        """⚠ 登记已知缺口（不是"支持"）：十进制浮点**字面量后缀** `dd` 尚未进词法面。

        现状：`1.5dd` 被切成 `literal.number(1.5)` + `id(dd)` ⇒ `_Decimal64 x = 1.5dd;`
        整条声明解析失败。归属与理由（两条证据）见 `grammar/c/plugins/c23/20_decimal.toml`
        头注与 `TODO.md`：后缀属核心基线 `base/_number.toml`（档位语义），插件侧另声明会被
        `deep_merge` 的"列表后者覆盖"顶掉核心数字形态。本用例把现状钉住——修好后它会红，
        提醒同步文档。
        """
        env = _env()
        kinds = [t for t, _ in env["tokens"]("1.5dd")]
        assert kinds == ["literal.number", "id"], kinds
        assert env["lint"]("_Decimal64 x = 1.5dd;\n") != [], "缺口已闭合？请同步文档与 TODO"

    def test_c23_spellings_reuse_the_c11_hosts(self, restore_language):
        """小写拼写与 c11 的 `_` 版**挂同一个宿主**（同构造异拼写 = 各写一条同形规则）。

        约定与代价（同一构造两个节点名）见 `16_alignas_alias.toml` 头注。这里守的是
        "宿主选择与 c11 一致"——否则 `alignas` 与 `_Alignas` 的可达位点会漂移。
        """
        rules = _env()["rules"]
        quals = " ".join(str(p) for p in rules["TypeQualifier"].production)
        store = " ".join(str(p) for p in rules["StorageClass"].production)
        for name in ("AlignasC23Spec", "AlignasC23TypeSpec"):
            assert f"@{name}" in quals, f"TypeQualifier 缺 @{name}：{quals}"
        assert "@ThreadLocalC23Spec" in store, store
        for host in ("PrimaryExpr", "PostfixExpr"):
            joined = " ".join(str(p) for p in rules[host].production)
            assert "@AlignofC23Expr" in joined, f"{host} 的原子清单缺 @AlignofC23Expr：{joined}"

    def test_static_assert_block_scope_is_injected(self, restore_language):
        """小写 `static_assert` 的**块作用域**靠注入核心 `Stmt`（旧注说"不可用"已作废）。

        ⚠ 这是本轮修掉的一条**过期边界**：c23 头注曾写块作用域要"改核心 `Stmt` 选择器"
        因而做不了——现役直接注入就是"加一支"，与 c11 的 `_Static_assert` 同一做法。
        """
        rules = _env()["rules"]
        stmt = " ".join(str(p) for p in rules["Stmt"].production)
        assert "@StaticAssertC23Decl" in stmt, stmt

    def test_injections_are_declared_in_plugin_files(self, restore_language):
        want = {
            "10_static_assert_alias.toml": ("@Stmt",),
            "11_nullptr.toml": ("@PrimaryExpr.production[0]", "@PostfixExpr.production[0]"),
            "12_bool_literal.toml": ("@PrimaryExpr.production[0]", "@PostfixExpr.production[0]"),
            "13_bool_type.toml": ("@SimpleType.production[0]",),
            "14_typeof.toml": ("@SimpleType.production[0]",),
            "15_constexpr.toml": ("@StorageClass.production[0]",),
            "16_alignas_alias.toml": ("@TypeQualifier.production[0]",),
            "17_alignof_alias.toml": ("@PrimaryExpr.production[0]", "@PostfixExpr.production[0]"),
            "18_thread_local_alias.toml": ("@StorageClass.production[0]",),
            "19_bitint.toml": ("@SimpleType.production[0]",),
            "20_decimal.toml": ("@SimpleType.production[0]",),
        }
        for fname, targets in want.items():
            path = ROOT_DIR / "grammar" / "c" / "plugins" / "c23" / fname
            with open(path, "rb") as f:
                data = tomllib.load(f)
            rules_with_inject = [
                k for k, v in data.items() if isinstance(v, dict) and "inject" in v
            ]
            for rule in rules_with_inject:
                got = tuple(data[rule]["inject"]["targets"])
                assert got == targets, f"{fname}:{rule} {got} != {targets}"


class TestTierDiscrimination:
    """档位判据：核心基线档下这些词不是关键字（当标识符/表达式），c23 档才是新节点。"""

    def test_baseline_tier_treats_them_as_plain_identifiers(self, tmp_path):
        import re
        import shutil

        dst = tmp_path / "lang"
        shutil.copytree(str(ROOT_DIR / "grammar" / "c"), dst, dirs_exist_ok=True)
        tpc = dst / "tpc.toml"
        tpc.write_text(
            re.sub(r"enabled = \[[^\]]*\]", "enabled = []",
                   tpc.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        pack = str(dst)
        ConfigRegistry.load_language(pack, plugins_dir=os.path.join(pack, "plugins"))
        rules = setup_grammar(pack, GrammarRulesRegister())
        stmt = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        parser = Parser(
            rules_dir=pack, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
        )
        lexer = Lexer(rules_dir=pack)
        for src, node in (("int *p = nullptr;\n", "NullptrLiteral"),
                          ("bool flag;\n", "BoolType"),
                          ("constexpr int n = 4;\n", "ConstexprSpec")):
            ast = parser.parse(lexer.tokenize(src))
            names = {n.node_name for n in iter_nodes(ast)} if ast is not None else set()
            assert node not in names, f"基线档不该有 {node}（{src.strip()!r}）：{sorted(names)}"
