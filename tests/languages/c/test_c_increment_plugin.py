"""tests/languages/c/test_c_increment_plugin.py — C 包的**增量插件形态**验证。

目标（0.1.3 目标 ①）："核心基线 + 标准增量插件"的组合形态。本文件验证五件事：

1. **增量住在插件目录里**：`StaticAssertDecl` 只出现在 `grammar/c/plugins/c11/` 下，
   核心基线文件（`00_*`/`01_*`/`02_*`/`03_*`）**不含**它——"加标准"= 加插件，不改基座文件；
2. **插件随包生效**：`setup_grammar("grammar/c")` 的规则表里**有**该规则、词法扩展也生效
   （`_Static_assert` 是关键字）；
3. **增量往核心交替里「加一支」而不是「改一支」**：核心 `Stmt` 选择器经**声明的注入**
   （`[StaticAssertDecl.inject] targets = ["@Stmt"]`）获得该候选，原候选一支不少、序不变；
4. **两处作用域都进 AST**：文件作用域（`is_statement` + 全局语句发现）与**块作用域**
   （注入进 `Stmt` 交替，并经传播覆盖 if/while/… 的 body 位）——C11 §6.7.4 两处都合法；
5. **解析形态确实变了**：`_Static_assert(1, "x");` → `StaticAssertDecl`（条件与消息都挂上）。

⚠ **历史更正（2026-09-26 实测）**：本文件原先断言"核心 `Stmt` 选择器里**不能有**
增量规则"，并以"块作用域需在核心 `Stmt` 里加分支 ⇒ 留待注入机制补『改』路径"为据。
**两条都不成立**：现役 `inject_productions` 的**直接注入**就是把 `@ExtRule` 作为候选并进
目标规则 production 的树（`insert_choice_candidate`），正是"往既有交替里加一支"——
缺的只是本插件没写那行声明。判据随之升级为"原候选不少 + 新增一支 + 来源可追"。

**启用入口（实测）**：语言包 `tpc.toml` 的 `[plugins] enabled` 是**运行时启用清单**——
它决定哪些插件目录的声明被合并（含 `[lexer] token_ext`）。⚠ 曾把这份清单当成"打包面
装饰"，是错的：加它之前 `_Static_assert` 一直是标识符；加上后立刻成为关键字。故 ROADMAP
说的"启用组合等效某标准"**在运行时可表达**；"同一次进程内切两档"也已是**一等参数**
（`ConfigRegistry.load_language(pack, enabled=[…])`，2026-09-26 落地）——
档位矩阵见 `test_c_standard_tiers.py`，本文件只按包默认档（= c23 全档）验证增量形态。
"""

import os
import tomllib
from pathlib import Path

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister, iter_nodes
from lexer import Lexer
from linter.scanner import LinterScanner
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from renderer import Renderer

ROOT_DIR = Path(__file__).resolve().parents[3]
_PACK = "grammar/c"
_PLUGINS = os.path.join(_PACK, "plugins")
_SRC = '_Static_assert(sizeof(int) > 0, "int must be non-empty");\n'

# 该样本不依赖 sizeof 的规则（本包尚未做 sizeof）——用最小可用条件
_SRC_MIN = '_Static_assert(1, "always true");\n'
_BLOCK_SRC = 'void f(void) {\n    _Static_assert(1, "x");\n}\n'
_IF_BODY_SRC = 'void f(int a) {\n    if (a)\n        _Static_assert(1, "x");\n}\n'


def _env() -> dict:
    """加载 C 包 + 其 plugins/，返回 {rules, parse, render, lint}。

    ⚠ 实测机制（两件事走**不同**路径）：
      · **规则文件**：`setup_grammar` 会扫描 `<pack>/plugins/`，故规则自动进来；
      · **词法扩展**（`[lexer] token_ext`）：必须经 `ext_dirs`（如 verilog 测试的
        `LinterScanner(rules_dir=…, ext_dirs=['…/plugins'])`）——只靠
        `ConfigRegistry.load_language(pack, plugins_dir=…)` 注册才生效——只传 pack
        时 `_Static_assert` 仍是标识符（症状：`_Static_assert(1, "x");` 解析成
        `ExprStmt`（当函数调用）而不是插件的 `StaticAssertDecl`）。
    """
    ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS)
    register = GrammarRulesRegister()
    rules = setup_grammar(_PACK, register, ext_dirs=[_PLUGINS])
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


def _names(ast) -> list[str]:
    return [n.node_name for n in (getattr(ast, "sub_node", []) or [])]


def _stmt_candidates(rules) -> list[str]:
    """`Stmt` 选择器的候选规则名（production 是单条裸交替 `@A|@B|…`）。"""
    prods = getattr(rules["Stmt"], "production", [])
    out: list[str] = []
    for prod in prods:
        for part in str(prod).split("|"):
            part = part.strip()
            if part.startswith("@"):
                out.append(part.lstrip("@"))
    return out


def _core_stmt_candidates() -> list[str]:
    """核心基线文件里 `Stmt` 声明的候选（不经引擎，直接从 TOML 读）。"""
    path = ROOT_DIR / "grammar" / "c" / "03_statements.toml"
    with open(path, "rb") as f:
        data = tomllib.load(f)
    out: list[str] = []
    for prod in data["Stmt"]["parser"]["production"]:
        for part in str(prod).split("|"):
            part = part.strip()
            if part.startswith("@"):
                out.append(part.lstrip("@"))
    return out


class TestPluginIsLoadedWithPack:
    def test_rule_present(self, restore_language):
        rules = _env()["rules"]
        assert "StaticAssertDecl" in rules

    def test_construct_parses_into_plugin_node(self, restore_language):
        """`_Static_assert(1, "x");` → 插件的 `StaticAssertDecl`。

        ⚠ **接通条件（实测得出，勿再按"打包面"理解）**：插件必须在语言包
        `tpc.toml` 的 `[plugins] enabled` 清单里 —— 那份清单是**运行时启用清单**，
        `load_language(pack, plugins_dir=…)` 只在被列出的插件上合并声明（含
        `[lexer] token_ext` 的词法扩展）。对照证据：verilog 的 `nand`（plugin 关键字）
        在 verilog 下**无需任何 ext_dirs** 即为关键字，因为 verilog 的 `enabled`
        列了 gates。
        """
        ast = _env()["parse"](_SRC_MIN)
        assert _names(ast) == ["StaticAssertDecl"], _names(ast)

    def test_condition_and_message_are_bound(self, restore_language):
        ast = _env()["parse"](_SRC_MIN)
        assert ast is not None
        node = ast.sub_node[0]
        assert node.cond.node_name == "Number"
        # `message` 绑定的是 **token**（production 里直接写 `literal.string`），
        # 故其节点名即 token 类型——不是 `StringLiteral` 那条规则（规则只在表达式位置用）。
        assert node.message.node_name == "literal.string"


class TestIncrementLivesOutsideBaseline:
    def test_rule_declared_only_in_plugin_dir(self, restore_language):
        """`StaticAssertDecl` 只在插件目录里声明——核心基线文件不含它。

        这是"加标准 = 加插件，不改基座"的可机械检查判据（扫描文件而非读规则表）。
        """
        pack = ROOT_DIR / "grammar" / "c"
        core_hits = [
            p.relative_to(pack).as_posix()
            for p in pack.glob("*.toml")
            if "StaticAssertDecl" in p.read_text(encoding="utf-8")
        ]
        plugin_hits = [
            p.relative_to(pack).as_posix()
            for p in (pack / "plugins").rglob("*.toml")
            if "StaticAssertDecl" in p.read_text(encoding="utf-8")
        ]
        assert core_hits == [], f"核心基线被增量污染：{core_hits}"
        assert plugin_hits, "插件目录里没有该规则的声明"


class TestIncrementAddsCandidateNotRewrites:
    """增量往核心 `Stmt` 交替里**加一支**（不是改一支），且那一支**来源可追**。"""

    def test_plugin_candidate_present(self, restore_language):
        rules = _env()["rules"]
        assert "StaticAssertDecl" in _stmt_candidates(rules)

    def test_all_core_candidates_preserved_in_order(self, restore_language):
        """原候选一支不少、相对序不变——"加一支"的可证伪判据。

        期望值**从核心 TOML 现读**（不硬抄一份进测试：抄一份只会在两处一起漂）。
        """
        got = _stmt_candidates(_env()["rules"])
        want = _core_stmt_candidates()
        pos = 0
        for name in want:
            assert name in got[pos:], f"核心候选 {name} 丢失或次序被打乱：{got}"
            pos = got.index(name, pos) + 1

    def test_injection_is_declared_in_plugin(self, restore_language):
        """来源可追：那一支来自插件**声明**的注入，而不是核心文件被手改。

        引擎不认识"StaticAssertDecl"这个名字；`[X.inject] targets` 是声明面。
        """
        path = ROOT_DIR / "grammar" / "c" / "plugins" / "c11" / "10_static_assert.toml"
        with open(path, "rb") as f:
            data = tomllib.load(f)
        assert data["StaticAssertDecl"]["inject"]["targets"] == ["@Stmt"]

    def test_core_stmt_selector_source_unchanged(self, restore_language):
        """核心 `03_statements.toml` 的 `Stmt` 候选仍等于读出来的那批（没有增量名）。"""
        assert "StaticAssertDecl" not in _core_stmt_candidates()


class TestBothScopes:
    """C11 §6.7.4：静态断言在**文件作用域与块作用域**都合法。"""

    def test_file_scope(self, restore_language):
        assert _names(_env()["parse"](_SRC_MIN)) == ["StaticAssertDecl"]

    def test_block_scope_in_function_body(self, restore_language):
        """函数体内可用——**本条是注入落地的直接判据**（此前整条函数解析失败）。"""
        ast = _env()["parse"](_BLOCK_SRC)
        assert _names(ast) == ["FuncDef"], _names(ast)

    def test_block_scope_in_if_body(self, restore_language):
        """传播注入：`if`/`while` 等 body 位也认（这些规则引用 `@Stmt`）。"""
        ast = _env()["parse"](_IF_BODY_SRC)
        assert _names(ast) == ["FuncDef"], _names(ast)

    def test_block_scope_render_faithful_and_idempotent(self, restore_language):
        env = _env()
        out = env["render"](_BLOCK_SRC)
        assert out == _BLOCK_SRC.rstrip("\n"), repr(out)
        assert env["render"](out + "\n") == out

    def test_block_scope_lints_clean(self, restore_language):
        assert _env()["lint"](_BLOCK_SRC) == []


# ── c11 其余语法增量（表达式原子位 / 说明符位）────────────────
# 每个构造一条声明式用例：源码 / 期望节点名 / 插入位（哪条核心规则的交替被"加了一支"）
_C11_INCREMENTS = [
    ("_Alignof", "int a = _Alignof(int);\n", "AlignofExpr"),
    ("_Alignof 结构体类型名", "unsigned n = _Alignof(struct s);\n", "AlignofExpr"),
    ("_Alignof 参与二元运算", "int b = _Alignof(int) * 2;\n", "AlignofExpr"),
    ("_Generic 单关联", "int g1 = _Generic(x, default: 7);\n", "GenericSelection"),
    ("_Generic 多关联", "int g2 = _Generic(x, char: 1, long: 2, default: 3);\n",
     "GenericSelection"),
    ("_Noreturn 原型", "_Noreturn void die(void);\n", "NoreturnSpec"),
    ("_Noreturn 在存储类之后", "static _Noreturn void die2(void);\n", "NoreturnSpec"),
    ("_Thread_local", "_Thread_local int tls;\n", "ThreadLocalSpec"),
    ("_Thread_local 与 static", "static _Thread_local int tls2;\n", "ThreadLocalSpec"),
    # `_Alignas` / `_Atomic`（2026-09-26 批次）——说明符位增量；注入点不同于上面几项：
    # 没有"最窄公共点"（`_Alignas`）或只有限位符位一支（`_Atomic`），见 15/16 插件头注。
    ("_Alignas 常量表达式", "_Alignas(16) char buf[64];\n", "AlignasConstSpec"),
    ("_Alignas 说明符序列其余位", "int _Alignas(8) x;\n", "AlignasConstSpec"),
    ("_Alignas 类型名形态", "_Alignas(double) char c;\n", "AlignasTypeSpec"),
    ("_Atomic 限定符在首位", "_Atomic int x;\n", "AtomicSpec"),
    ("_Atomic 限定符在其余位", "int _Atomic x;\n", "AtomicSpec"),
    ("_Atomic(T) 说明符形态", "_Atomic(int) x;\n", "AtomicSpec"),
]


class TestC11SyntaxIncrements:
    """c11 的其余语法增量：`_Alignof` / `_Generic` / `_Noreturn` / `_Thread_local`。

    四者各自落在核心基线的一个**既有交替**上（原子清单两处 / 函数说明符 / 存储类），
    都靠声明的注入"加一支"落地——本类同时是这四个注入点的回归守。
    """

    @pytest.mark.parametrize("label,src,node", _C11_INCREMENTS,
                             ids=[c[0] for c in _C11_INCREMENTS])
    def test_parses_into_expected_node(self, restore_language, label, src, node):
        ast = _env()["parse"](src)
        assert ast is not None
        names = {n.node_name for n in iter_nodes(ast)}
        assert node in names, f"{label}: 期望 {node}，实得 {sorted(names)}"

    @pytest.mark.parametrize("label,src,node", _C11_INCREMENTS,
                             ids=[c[0] for c in _C11_INCREMENTS])
    def test_render_faithful_and_idempotent(self, restore_language, label, src, node):
        del label, node
        env = _env()
        out = env["render"](src)
        assert out == src.rstrip("\n"), repr(out)
        assert env["render"](out + "\n") == out

    @pytest.mark.parametrize("label,src,node", _C11_INCREMENTS,
                             ids=[c[0] for c in _C11_INCREMENTS])
    def test_lints_clean(self, restore_language, label, src, node):
        del label, node
        assert _env()["lint"](src) == []

    def test_atom_increments_reach_both_atom_lists(self, restore_language):
        """原子类增量必须注进**两处**原子清单（`PrimaryExpr` 与 `PostfixExpr` 的 head）。

        核心基线的原子清单刻意写两处（`00_expressions.toml` 头注：一处是语句起点种子、
        一处防 FOLLOW 被拦），只注一处会得到"能当表达式、但不能当后缀链头"的半通形态。
        """
        rules = _env()["rules"]
        for name in ("AlignofExpr", "GenericSelection"):
            for host in ("PrimaryExpr", "PostfixExpr"):
                joined = " ".join(str(p) for p in rules[host].production)
                assert f"@{name}" in joined, f"{host} 的原子清单缺 @{name}：{joined}"

    def test_specifier_increments_attach_to_the_right_host(self, restore_language):
        rules = _env()["rules"]
        func = " ".join(str(p) for p in rules["FuncSpec"].production)
        store = " ".join(str(p) for p in rules["StorageClass"].production)
        assert "@NoreturnSpec" in func, func
        assert "@ThreadLocalSpec" in store, store

    def test_injections_are_declared_in_plugin_files(self, restore_language):
        """来源可追：四个注入点都由插件 TOML 声明，核心基线文件一行未动。"""
        want = {
            "11_alignof.toml": ("@PrimaryExpr.production[0]", "@PostfixExpr.production[0]"),
            "13_noreturn.toml": ("@FuncSpec.production[0]",),
            "14_thread_local.toml": ("@StorageClass.production[0]",),
        }
        for fname, targets in want.items():
            path = ROOT_DIR / "grammar" / "c" / "plugins" / "c11" / fname
            with open(path, "rb") as f:
                data = tomllib.load(f)
            rule = next(k for k, v in data.items() if isinstance(v, dict) and "inject" in v)
            got = tuple(data[rule]["inject"]["targets"])
            assert got == targets, f"{fname}: {got} != {targets}"

    def test_generic_association_list_is_structural(self, restore_language):
        """多关联要**真进 AST**（不是"解析通过但只留一条"）：3 条关联 → 3 个 GenericAssoc。"""
        ast = _env()["parse"]("int g = _Generic(x, char: 1, long: 2, default: 3);\n")
        assert ast is not None
        kinds = [n.node_name for n in iter_nodes(ast)]
        assert kinds.count("GenericAssoc") == 3, kinds

    def test_generic_default_association_kind(self, restore_language):
        ast = _env()["parse"]("int g = _Generic(x, default: 7);\n")
        assert ast is not None
        assoc = next(n for n in iter_nodes(ast) if n.node_name == "GenericAssoc")
        # 两支都是**节点**（形态一致）：default 支是 keyword token，类型名支是 `TypeName` 规则
        assert assoc.kind.node_name == "keyword.default", assoc.kind
        typed = _env()["parse"]("int g = _Generic(x, char: 1);\n")
        assert typed is not None
        assoc2 = next(n for n in iter_nodes(typed) if n.node_name == "GenericAssoc")
        assert assoc2.kind.node_name == "TypeName", assoc2.kind


# ── 说明符位增量：`_Alignas` / `_Atomic`（2026-09-26）──────────────────
# 这两个构造的注入点形态与上面几项**不同**，且都撞过引擎的一条性质（"选择器只在
# **同一元素内**换候选，不跨元素/跨兄弟回溯"），故单独一类把经验钉成判据：
#   · `_Alignas`：说明符位在本包由 **6 条规则**分别表达（没有统一的
#     declaration-specifiers），共同的最窄点是 `@TypeQualifier` ⇒ 一次注入六处生效；
#   · `_Atomic`：两种形态（限定符 / `_Atomic(T)`）**必须写在一条规则里**（可选组）。
#     拆成两条规则时 `_Atomic(int) x;` 会先命中单 token 那条、随后元素失败且**不回头**
#     ⇒ 整条声明解析失败（实测空 AST）——本类的 `test_both_forms_in_one_env` 是它的回归守。

# 逐字还原用例：(标签, 源码, 期望节点)
_SPECIFIER_SLOT_FAITHFUL = [
    ("_Alignas 块作用域", "void f(void) {\n    _Alignas(16) int x;\n}\n", "AlignasConstSpec"),
    ("_Alignas 结构成员", "struct S {\n    _Alignas(8) int x;\n};\n", "AlignasConstSpec"),
    ("_Alignas 参数位", "void f(_Alignas(8) int x);\n", "AlignasConstSpec"),
    ("_Alignas 类型名位 sizeof", "int n = sizeof(_Alignas(8) int);\n", "AlignasConstSpec"),
    ("_Atomic 块作用域", "void f(void) {\n    _Atomic int x;\n}\n", "AtomicSpec"),
    ("_Atomic(T) 块作用域", "void f(void) {\n    _Atomic(int) x;\n}\n", "AtomicSpec"),
    ("_Atomic 结构成员", "struct S {\n    _Atomic int x;\n};\n", "AtomicSpec"),
    ("_Atomic 参数位", "void f(_Atomic int x);\n", "AtomicSpec"),
    ("_Atomic(T) 类型名位 sizeof", "int n = sizeof(_Atomic(int));\n", "AtomicSpec"),
]

# 说明符位六处（`_Alignas` 要覆盖全部：任一处漏掉就有一种合法写法进不来）
_SPECIFIER_SLOT_HOSTS = [
    "Declaration",
    "SpecRest",
    "FuncDef",
    "MemberSpec",
    "ParamSpec",
    "TypeName",
]


class TestC11SpecifierSlotIncrements:
    """`_Alignas`（C11 §6.7.5）与 `_Atomic`（§6.7.2.4/§6.7.3）——说明符位增量。"""

    @pytest.mark.parametrize("label,src,node", _SPECIFIER_SLOT_FAITHFUL,
                             ids=[c[0] for c in _SPECIFIER_SLOT_FAITHFUL])
    def test_parses_into_expected_node(self, restore_language, label, src, node):
        ast = _env()["parse"](src)
        assert ast is not None, label
        names = {n.node_name for n in iter_nodes(ast)}
        assert node in names, f"{label}: 期望 {node}，实得 {sorted(names)}"

    @pytest.mark.parametrize("label,src,node", _SPECIFIER_SLOT_FAITHFUL,
                             ids=[c[0] for c in _SPECIFIER_SLOT_FAITHFUL])
    def test_render_faithful_and_idempotent(self, restore_language, label, src, node):
        del label, node
        env = _env()
        out = env["render"](src)
        assert out == src.rstrip("\n"), repr(out)
        assert env["render"](out + "\n") == out

    @pytest.mark.parametrize("label,src,node", _SPECIFIER_SLOT_FAITHFUL,
                             ids=[c[0] for c in _SPECIFIER_SLOT_FAITHFUL])
    def test_lints_clean(self, restore_language, label, src, node):
        del label, node
        assert _env()["lint"](src) == []

    def test_both_forms_in_one_env(self, restore_language):
        """`_Atomic` 两种形态**同一次加载**下都要进 AST。

        ⚠ 这条是"拆成两条规则就挂"的回归守：单 token 的限定符形态若排在
        `_Atomic(T)` 之前，后者会因"命中后不回头"而整条失败（实测空 AST）。
        三种写法各自断言，且**同一个 env**（同一份规则表）下连续跑。
        """
        env = _env()
        for src in ("_Atomic int x;\n", "int _Atomic x;\n", "_Atomic(int) x;\n",
                    "_Atomic(int *) p;\n"):
            ast = env["parse"](src)
            assert ast is not None, src
            names = {n.node_name for n in iter_nodes(ast)}
            assert "AtomicSpec" in names, f"{src} → {sorted(names)}"

    def test_atomic_two_forms_live_in_one_rule(self, restore_language):
        """形态收在一个规则里（可选组），不是"两条规则 + 两个注入点"。

        结构判据（配合上一条行为判据）：`AtomicSpec` 的 production 里那组
        `( … )?` 就是 `_Atomic(T)` 形态；`TypeQualifier` 的候选里**不应**再出现
        被拆开的 `@AtomicQual` / `@AtomicTypeSpec`（那是撞过墙的形态）。
        """
        rules = _env()["rules"]
        assert "AtomicSpec" in rules, sorted(rules)
        prod = " ".join(str(p) for p in rules["AtomicSpec"].production)
        assert "?" in prod, prod
        quals = " ".join(str(p) for p in rules["TypeQualifier"].production)
        assert "@AtomicSpec" in quals, quals
        assert "@AtomicQual" not in quals and "@AtomicTypeSpec" not in quals, quals

    def test_alignas_reaches_all_six_specifier_slots(self, restore_language):
        """`_Alignas` 经 `@TypeQualifier` 一次注入、六处说明符位全生效。

        这 6 处就是本包说明符位的全集（没有统一的 declaration-specifiers 规则）——
        漏一处 = 某种合法写法静默进不来（成员 / 参数 / 类型名就是漏点）。
        """
        rules = _env()["rules"]
        for host in _SPECIFIER_SLOT_HOSTS:
            joined = " ".join(str(p) for p in rules[host].production)
            assert "@AlignasConstSpec" in joined, f"{host} 缺 _Alignas：{joined}"

    def test_core_baseline_files_untouched(self, restore_language):
        """增量名不出现在核心基线文件里（"加标准 = 加插件"的可机械检查判据）。"""
        pack = ROOT_DIR / "grammar" / "c"
        hits = [
            p.name
            for p in pack.glob("*.toml")
            if any(
                name in p.read_text(encoding="utf-8")
                for name in ("AlignasConstSpec", "AlignasTypeSpec", "AtomicSpec")
            )
        ]
        assert hits == [], f"核心基线被增量污染：{hits}"

    def test_injection_is_declared_in_plugin_files(self, restore_language):
        """来源可追：两个插件文件各自声明注入目标，核心文件一行未动。"""
        want = {
            "15_alignas.toml": ("AlignasConstSpec", "AlignasTypeSpec"),
            "16_atomic.toml": ("AtomicSpec",),
        }
        for fname, rule_names in want.items():
            path = ROOT_DIR / "grammar" / "c" / "plugins" / "c11" / fname
            with open(path, "rb") as f:
                data = tomllib.load(f)
            for rule in rule_names:
                got = tuple(data[rule]["inject"]["targets"])
                assert got == ("@TypeQualifier.production[0]",), f"{fname}:{rule} → {got}"
