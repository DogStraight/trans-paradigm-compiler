"""tests/languages/c/test_c_standard_conformance.py — 标准等价断言面（接受 + 拒绝双向）。

ROADMAP「阶段 5 标准等效验证」缺的那片：**按标准分档、每条构造各断言一次接受与一次拒绝**。
第一批 = 静态断言族（C11 `_Static_assert` / C23 `static_assert`，含**三处作用域**：文件 /
块 / struct·union 成员表）；另附仍开着的 C11/C23 语法面缺口（`xfail(strict=True)` 钉住，
修好即变红提醒移出清单）。

## 判据三态（本包"接受域"的口径，见 `docs/gaps/gap-language-pack-scope.md`）

    档位 ≥ 构造所属标准：accepted —— 解析成插件节点 + linter 零诊断 + 渲染 token 序列不变 + 幂等
    档位 < 所属标准：generic / rejected 两态，**都要断言**（"未声明关键字 ≠ 拒绝"）：
      · generic —— 关键字未声明时被当作普通标识符/函数调用照常解析（C 语法本就宽进）；
      · rejected —— 新形态整体套不进任何既有语句形态 ⇒ **空 AST**（不静默当标识符）。

## oracle（外部裁判）

`gcc 16.1.0`（MinGW-W64）`-std=c11|… -pedantic-errors -fsyntax-only` 实测同一批样本；
结论写在 `_GAPS` 每条的注释里，原始命令见 gap 档「C 标准等效缺口」。复现：

    gcc -std=c23 -pedantic-errors -fsyntax-only case.c

## 与既有门禁的分工（不复制门禁）

`test_c_standard_tiers.py` 守**档位机制**（同进程切档 / 缓存键 / 启用清单）与各增量的
"从哪一档起出现节点"矩阵；本文件只补它没有的那一半：**拒绝面**、**下档三态**、
**标准缺口清单**——接受面的正向断言在那边，不在此重复。
"""

import os

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

_PACK = "grammar/c"
_PLUGINS = os.path.join(_PACK, "plugins")

_TIERS = {
    "baseline": [],
    "c11": ["c11"],
    "c17": ["c11", "c17"],
    "c23": ["c11", "c17", "c23"],
}

# 静态断言族的**拒绝面**：同一构造形态的非法/超出标准样本，必须在其所属档位被拒。
# 判据 = ① 不出现插件节点（不被误读成别的语句）② 解析不出顶层节点（空 AST）
#        ③ linter（生产路径）给出诊断——三条缺一都算"静默接受"。
_REJECT_MATRIX = [
    ("_Static_assert 缺消息（C11 两参必选）", "_Static_assert(1);\n", "c11",
     "C11 §6.7.4 static_assert-declaration 两参"),
    ("_Static_assert 缺消息（C17 同上）", "_Static_assert(1);\n", "c17",
     "C17 沿用 C11 §6.7.4；消息可省是 C23 才有的（档位门控前这条会被 c23 规则漏进来）"),
    ("_Static_assert 消息不是字符串字面量", '_Static_assert(1, 2);\n', "c11",
     "同上：第二实参必须是 string-literal"),
    ("_Static_assert 多一个实参", '_Static_assert(1, "x", 3);\n', "c11", "同上"),
    ("static_assert 缺条件（空实参）", "static_assert();\n", "c23",
     "C23 §6.7.10：消息可省但条件必选"),
    ("static_assert 消息不是字符串字面量", "static_assert(1, 2);\n", "c23", "同上"),
    ("static_assert 多一个实参", 'static_assert(1, "x", 3);\n', "c23", "同上"),
]

# 下档三态：同一形态在**未达其所属标准**的档位上的实测归宿（"未声明关键字 ≠ 拒绝"）。
_BELOW_TIER_STATE = [
    ("_Static_assert 当普通调用（基线档）", '_Static_assert(1, "x");\n', "baseline", "generic"),
    ("static_assert 单参当普通调用（c11 档）", "static_assert(1);\n", "c11", "generic"),
    ("static_assert 两参当普通调用（c11 档）", 'static_assert(1, "x");\n', "c11", "generic"),
    ("bool 当 typedef 名（基线档）", "bool f;\n", "baseline", "generic"),
    ("nullptr 当标识符（基线档）", "int *p = nullptr;\n", "baseline", "generic"),
    ("typeof 关键字未声明 ⇒ 整体不解析（基线档）", "typeof(int) z;\n", "baseline", "rejected"),
    ("_BitInt 同上（基线档）", "_BitInt(8) a;\n", "baseline", "rejected"),
    ("alignas 同上（基线档）", "alignas(16) char c;\n", "baseline", "rejected"),
]

# 标准等效**缺口清单**（oracle 实测 + tpc 对照；`xfail(strict=True)`：修好即变红提醒转正）。
# 每条 = (标签, 源码, 档位, 标准依据 + gcc 结论)
# ⚠ 成员表位（#35）、字面量前缀族 / 二进制常量（#37）、数字分隔符（#38）、
#   C23 单参下划线拼写 `_Static_assert(1)`（#41）已转正，移出本清单；
#   余 1 条：`enum e : int` 固定底层类型（core 的冒号位若由 c23 规则注入会漏进下档，
#   #40 门控后前置已解除、待实现）。
_GAPS = [
    ("C23 enum 固定底层类型", "enum e : int { A };\n", "c23",
     "C23 §6.7.2.2 enum-type-specifier；gcc -std=c23 OK"),
]


@pytest.fixture(autouse=True)
def _restore_language():  # pyright: ignore[reportUnusedFunction] — autouse fixture（按名发现）
    yield
    ConfigRegistry.load_language("grammar/verilog", plugins_dir="grammar/verilog/plugins")


def _env(tier: str) -> dict:
    """按档位加载 C 包，返回解析/渲染/lint 入口（**生产路径**：档位只走 `enabled=`）。

    ⚠ **不传 `ext_dirs=[plugins]`**（2026-10-21 循环 #41 修正）：那会把插件的规则文件
    当"显式扩展目录"无条件注册，绕过 ADR-0023 的档位门控（`ext_dirs` 按定义不受门控，
    见 ADR-0023「边界」）——测试里就变成"c11 档也加载 c23 规则"，判据被抬高接受域掩盖。
    生产入口（CLI/pipeline）的 `ext_dirs` 为空，插件规则只经 `load_all_components` 按档加载。
    """
    enabled = _TIERS[tier]
    ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=enabled)
    rules = setup_grammar(_PACK, GrammarRulesRegister())
    stmt = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=_PACK, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
    )
    lexer = Lexer(rules_dir=_PACK)

    def parse(src: str):
        return parser.parse(lexer.tokenize(src))

    def render(src: str) -> str:
        ast = parse(src)
        assert ast is not None, f"解析不出 AST：{src!r}"
        return Renderer(
            rules_dir=_PACK,
            line_comment_starts=lexer.line_terminating_comment_starts(),
        ).render(ast)

    return {
        "parse": parse,
        "render": render,
        "lint": lambda src: LinterScanner(
            rules_dir=_PACK, register=GrammarRulesRegister()
        ).scan(src),
        "tokens": lambda text: [
            (t.type, t.content)
            for t in lexer.tokenize(text)
            if t.type not in TRIVIA_TOKEN_TYPES
        ],
    }


class TestRejectSide:
    """静态断言族的**拒绝面**（每条构造"接受/拒绝各断言一条"里的拒绝那半）。"""

    @pytest.mark.parametrize(
        "label,src,tier,basis", _REJECT_MATRIX, ids=[c[0] for c in _REJECT_MATRIX]
    )
    def test_invalid_static_assert_is_rejected(self, label, src, tier, basis):
        env = _env(tier)
        ast = env["parse"](src)
        names = {n.node_name for n in iter_nodes(ast)} if ast is not None else set()
        for node in ("StaticAssertDecl", "StaticAssertC23Decl",
                     "StaticAssertC23MsgDecl", "StaticAssertC23NoMsgDecl"):
            assert node not in names, f"{label}：被误读成插件节点 {node}（{basis}）"
        # 空 AST：形态不属任何既有语句 ⇒ 整条不进树（发现阶段无 FIRST 命中）
        assert ast is not None
        assert not getattr(ast, "sub_node", None), f"{label}：不该解析出顶层节点"
        # 生产路径（linter）必须喊出来，不能静默吞掉
        assert env["lint"](src), f"{label}：linter 零诊断（静默接受非法形态）"


class TestBelowTierState:
    """下档三态：generic（被当作普通构造照常解析）/ rejected（整体不进树）。"""

    @pytest.mark.parametrize(
        "label,src,tier,state", _BELOW_TIER_STATE, ids=[c[0] for c in _BELOW_TIER_STATE]
    )
    def test_below_tier_state_is_as_documented(self, label, src, tier, state):
        env = _env(tier)
        ast = env["parse"](src)
        names = {n.node_name for n in iter_nodes(ast)} if ast is not None else set()
        # 无论哪态，插件节点都不该出现（档位 = 接受域的判据是"解析成哪个节点"）
        for node in ("StaticAssertDecl", "StaticAssertC23Decl", "BoolType",
                     "NullptrLiteral", "TypeofSpec", "BitIntSpec",
                     "AlignasC23Spec", "AlignasConstSpec"):
            assert node not in names, f"{label}：未达档位却出现 {node}"
        top = getattr(ast, "sub_node", None) or []
        if state == "generic":
            assert top, f"{label}：应为 generic（照常解析）却得到空 AST"
        else:
            assert not top, f"{label}：应为 rejected（整体不进树）却解析出 {[n.node_name for n in top]}"


class TestLiteralForms:
    """字面量**前缀族**与二进制常量的端到端接受面（C99 `L` / C11 `u`·`U`·`u8` / C23 `u8` 字符·二进制）。

    判据 = 档位 >= 所属标准时：进 AST + linter 零诊断 + 渲染 token 序列逐项相同 + 幂等；
    档位不足时：**整体不进树**（词法切分会退化为 id + literal.string 两 token，语法自然不收）。
    词法层的逐档切分判据在 `test_c_lexer.py::TestLiteralPrefixTiers`（不复制，只补端到端）。
    """

    _ACCEPT = [
        ("C99 宽字符串（基线）", 'char *s = L"x";\n', "baseline"),
        ("C99 宽字符（基线）", "char c = L'x';\n", "baseline"),
        ("C11 Unicode 字符串 u", 'char *s = u"x";\n', "c11"),
        ("C11 Unicode 字符串 U", 'char *s = U"x";\n', "c11"),
        ("C11 UTF-8 字符串 u8", 'char *s = u8"x";\n', "c11"),
        ("C11 Unicode 字符 u", "char c = u'x';\n", "c11"),
        ("C23 UTF-8 字符 u8", "char c = u8'x';\n", "c23"),
        ("C23 二进制常量", "int n = 0b1010;\n", "c23"),
        ("C23 二进制常量 + 后缀", "unsigned n = 0B1010ULL;\n", "c23"),
        # ── C23 数字分隔符（§6.4.4.1；引擎 `[[number.based]] digit_separator`）──
        ("C23 十进制数字分隔符", "int n = 1'000'000;\n", "c23"),
        ("C23 十六进制数字分隔符", "int n = 0x1'F;\n", "c23"),
        ("C23 八进制数字分隔符", "int n = 0'7;\n", "c23"),
        ("C23 二进制数字分隔符", "int n = 0b1'0;\n", "c23"),
        ("C23 浮点数字分隔符", "double n = 1.5'0;\n", "c23"),
        ("C23 指数位分隔符", "double n = 1.0e1'0;\n", "c23"),
        ("C23 分隔符 + 后缀", "unsigned n = 1'000u;\n", "c23"),
        ("C11 前缀字符串作静态断言消息", 'static_assert(1, u8"msg");\n', "c11"),
    ]

    @pytest.mark.parametrize(
        "label,src,tier", _ACCEPT, ids=[c[0] for c in _ACCEPT]
    )
    def test_accepted_and_faithful(self, label, src, tier):
        env = _env(tier)
        ast = env["parse"](src)
        assert ast is not None and getattr(ast, "sub_node", None), f"{label}: 空 AST"
        assert env["lint"](src) == [], f"{label}: linter 有诊断"
        out = env["render"](src)
        assert env["tokens"](out) == env["tokens"](src), f"{label}: {src!r} → {out!r}"
        assert env["render"](out) == out, f"{label}: 不幂等"

    _REJECT = [
        ("C11 档不认 u8 字符（C23 才有）", "char c = u8'x';\n", "c11"),
        ("基线档不认 u 字符串（C11 才有）", 'char *s = u"x";\n', "baseline"),
        ("基线档不认 u8 字符串（C11 才有）", 'char *s = u8"x";\n', "baseline"),
        ("C11 档不认二进制常量（C23 才有）", "int n = 0b1010;\n", "c11"),
        ("C11 档不认数字分隔符（C23 才有）", "int n = 1'000'000;\n", "c11"),
        ("基线档不认数字分隔符", "int n = 1'000'000;\n", "baseline"),
    ]

    @pytest.mark.parametrize(
        "label,src,tier", _REJECT, ids=[c[0] for c in _REJECT]
    )
    def test_tier_mismatch_not_accepted(self, label, src, tier):
        env = _env(tier)
        ast = env["parse"](src)
        assert not getattr(ast, "sub_node", None), f"{label}: 未达档位却解析出了 AST"


class TestStaticAssertMemberPosition:
    """静态断言的**成员表位**（C11 §6.7.2.1：struct-declaration 含 static_assert-declaration）。

    实现口径 = 容器级**空槽位**（`StructBody = { (@StructMember|@StructMemberExtra)* }`，
    增量注入 `@StructMemberExtra`），不碰 `StructMember` 自身形态。判据：
      ① 增量节点进 `StructBody.members`，顺序与源一致；
      ② 空槽位不产生包装节点（`StructMemberExtra` 不进 AST）；
      ③ linter 零诊断（**顶层**同类语句不得被成员规则抢去分类——旧注入点的假红现场）；
      ④ 渲染 token 序列逐项相同 + 幂等。
    """

    _CASES = [
        ("C11 struct 成员", 'struct s { int a; _Static_assert(1, "x"); };\n',
         "c11", "StaticAssertDecl"),
        ("C11 union 成员", 'union u { int a; _Static_assert(1, "x"); };\n',
         "c11", "StaticAssertDecl"),
        ("C11 成员（首位）", 'struct s { _Static_assert(1, "x"); int a; };\n',
         "c11", "StaticAssertDecl"),
        ("C23 struct 成员两参", 'struct s { int a; static_assert(1, "x"); };\n',
         "c23", "StaticAssertC23MsgDecl"),
        ("C23 struct 成员单参", 'struct s { int a; static_assert(1); };\n',
         "c23", "StaticAssertC23NoMsgDecl"),
        ("C23 下划线拼写 struct 成员单参",
         "struct s { int a; _Static_assert(1); };\n",
         "c23", "StaticAssertC23UnderscoreNoMsgDecl"),
    ]

    @pytest.mark.parametrize("label,src,tier,node", _CASES, ids=[c[0] for c in _CASES])
    def test_member_position_accepted_and_faithful(self, label, src, tier, node):
        env = _env(tier)
        ast = env["parse"](src)
        assert ast is not None, label
        names = {n.node_name for n in iter_nodes(ast)}
        assert node in names, f"{label}: 缺 {node}（{sorted(names)}）"
        assert "StructMemberExtra" not in names, f"{label}: 空槽位应展平，不进 AST"
        assert env["lint"](src) == [], f"{label}: linter 有诊断"
        out = env["render"](src)
        assert env["tokens"](out) == env["tokens"](src), f"{label}: {src!r} → {out!r}"
        assert env["render"](out) == out, f"{label}: 不幂等"

    def test_members_order_preserved(self):
        """成员表顺序 = 源顺序（静态断言穿插在成员之间）。"""
        src = 'struct s { int a; _Static_assert(1, "x"); int b; };\n'
        ast = _env("c11")["parse"](src)
        body = next(n for n in iter_nodes(ast) if n.node_name == "StructBody")
        members = getattr(body, "members")
        kinds = [m.node_name for m in getattr(members, "items")]
        assert kinds == ["StructMember", "StaticAssertDecl", "StructMember"], kinds

    @pytest.mark.parametrize(
        "label,src,tier",
        [
            ("C11 成员位单参（C11 该拒）", "struct s { int a; _Static_assert(1); };\n", "c11"),
            ("C23 成员位空实参（C23 该拒）", "struct s { int a; static_assert(); };\n", "c23"),
        ],
        ids=["C11 成员位单参", "C23 成员位空实参"],
    )
    def test_member_position_rejects_invalid_shape(self, label, src, tier):
        env = _env(tier)
        names = {n.node_name for n in iter_nodes(env["parse"](src))} if env["parse"](src) else set()
        assert "StaticAssertDecl" not in names and "StaticAssertC23NoMsgDecl" not in names, label
        assert "StaticAssertC23UnderscoreNoMsgDecl" not in names, label
        assert env["lint"](src), f"{label}: linter 零诊断（静默接受非法形态）"


class TestC23UnderscoreNoMsg:
    """C23 §6.7.10 的**单参形态**对 `_Static_assert` 拼写同样成立（循环 #41）。

    缺口原样（gcc 接受、tpc 拒绝）：`_Static_assert(1);`——修法 = c23 插件新增同形规则
    `22_static_assert_no_msg.toml`，靠 ADR-0023 档位门控只在 c23 档加载（c11/c17 的
    "两参必选"拒绝面在 `TestRejectSide`，两档各一条）。判据：
      ① 三处作用域（文件 / 块 / if body；成员表位在 `TestStaticAssertMemberPosition`）
         都解析成 `StaticAssertC23UnderscoreNoMsgDecl` 且 `cond` 绑定到条件表达式；
      ② 与 c11 的 `_Static_assert(1, "x")` 规则**同首 token 并存**：两参形态不被本条抢走
         （`StaticAssertDecl` 仍在——同首 token 试解析区分）；
      ③ linter 零诊断 + 渲染 token 序列逐项相同 + 幂等。
    """

    _CASES = [
        ("C23 单参（文件作用域）", "_Static_assert(1);\n"),
        ("C23 单参（块作用域）", "void f(void) {\n    _Static_assert(1);\n}\n"),
        ("C23 单参（if body）", "void f(int a) {\n    if (a)\n        _Static_assert(1);\n}\n"),
    ]

    @pytest.mark.parametrize("label,src", _CASES, ids=[c[0] for c in _CASES])
    def test_accepted_in_c23(self, label, src):
        env = _env("c23")
        ast = env["parse"](src)
        assert ast is not None and getattr(ast, "sub_node", None), f"{label}: 空 AST"
        nodes = list(iter_nodes(ast))
        assert any(n.node_name == "StaticAssertC23UnderscoreNoMsgDecl" for n in nodes), (
            f"{label}: 缺 StaticAssertC23UnderscoreNoMsgDecl（{sorted(n.node_name for n in nodes)}）"
        )
        node = next(n for n in nodes if n.node_name == "StaticAssertC23UnderscoreNoMsgDecl")
        assert getattr(node, "cond", None) is not None, f"{label}: cond 未绑定"
        assert env["lint"](src) == [], f"{label}: linter 有诊断"
        out = env["render"](src)
        assert env["tokens"](out) == env["tokens"](src), f"{label}: {src!r} → {out!r}"
        assert env["render"](out) == out, f"{label}: 不幂等"

    def test_two_arg_underscore_form_not_stolen(self):
        """同首 token 两条规则靠试解析区分：两参形态仍走 c11 的 `StaticAssertDecl`。"""
        src = '_Static_assert(1, "x");\n'
        names = {n.node_name for n in iter_nodes(_env("c23")["parse"](src))}
        assert "StaticAssertDecl" in names, names
        assert "StaticAssertC23UnderscoreNoMsgDecl" not in names, names


class TestStandardGaps:
    """标准等效**缺口清单**（xfail strict：修好后变红，提醒把用例转正并删缺口条目）。

    ⚠ **缺陷态判据**：每条都是"gcc 接受、tpc 拒绝"的合法标准代码——断言的是
    **接受**（进 AST + linter 零诊断 + 渲染 token 序列不变 + 幂等）。当前全体不成立
    ⇒ xfail；修好一条就 red 一条，正是"缺口已修"的信号。清单与归属见
    `docs/gaps/gap-language-pack-scope.md`「C 标准等效缺口」。
    """

    @pytest.mark.parametrize(
        "label,src,tier,basis", _GAPS, ids=[c[0] for c in _GAPS]
    )
    @pytest.mark.xfail(strict=True, reason="C11/C23 语法面缺口（gcc 接受、tpc 拒绝），"
                                          "清单见 docs/gaps/gap-language-pack-scope.md")
    def test_standard_gap_is_currently_open(self, label, src, tier, basis):
        env = _env(tier)
        ast = env["parse"](src)
        assert ast is not None, f"{label}：解析不出 AST（{basis}）"
        assert getattr(ast, "sub_node", None), f"{label}：空 AST（{basis}）"
        assert env["lint"](src) == [], f"{label}：linter 有诊断（{basis}）"
        out = env["render"](src)
        assert env["tokens"](out) == env["tokens"](src), f"{label}：渲染 token 序列不同"
        assert env["render"](out) == out, f"{label}：渲染不幂等"
