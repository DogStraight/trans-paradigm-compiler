"""tests/languages/c/test_c_standard_tiers.py — 标准档位对照（**同进程切档**）。

验证 ROADMAP 的"标准等效"主张：**同一份语法资产**（核心基线 + 插件目录），只改
**启用组合**，就得到不同标准的语法接受域。启用组合有两个等价入口：

1. **包内** `tpc.toml` 的 `[plugins] enabled`（默认档位）；或
2. **引擎级 `enabled=` 覆盖参数**（`load_language/load_all/resolve`）——2026-09-26 落地，
   于是"同一次进程内切两档"不再需要 pack 副本。

    档位          enabled                  `_Static_assert`(c11)   `static_assert`(c23)
    核心基线档    []                       ExprStmt（当调用表达式）  ExprStmt
    c11 档        ["c11"]                  StaticAssertDecl         ExprStmt
    c11+c17 档    ["c11","c17"]            StaticAssertDecl         ExprStmt
    c23 全档      ["c11","c17","c23"]      StaticAssertDecl         StaticAssertC23Decl

⚠ **未声明关键字 ≠ 拒绝**：关键字没声明时，`_Static_assert(1, "x");` 会被当作
**普通函数调用**（`ExprStmt`）**静默接受**——C 语法本就宽进（调用未声明的函数合法）。
故档位判据看的是**解析成哪个节点**，而不是"有没有报错"。

⚠ **两处缓存是这类切换的经典陷阱**（本轮实测，`core/config_registry.py`）：
`_entries_source` 只比目录 ⇒ 同包切档复用上一档声明；`_resolve_cache` 的键不含档位
⇒ `Lexer`（走 `resolve`）拿回上一档 token。两处都已按 `(包, 档位)` 键控，并由
`TestTierCacheHygiene` 反向守。
"""

import os
import pathlib
import re
import shutil
import tomllib

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister, iter_nodes
from core.errors import ConfigError
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_PACK = os.path.join(ROOT, "grammar", "c")
_PLUGINS = os.path.join(_PACK, "plugins")

_C11_SRC = '_Static_assert(1, "x");\n'
_C23_SRC = 'static_assert(1, "x");\n'
# 块作用域形态（C11 §6.7.4 两处都合法）：档位判据要看"块内那支进没进 Stmt 交替"
_C11_BLOCK_SRC = 'void f(void) {\n    _Static_assert(1, "x");\n}\n'

# (构造, 源码, 期望节点, 首次出现的档位) —— "档位"= 从哪一档起该节点存在
_INCREMENT_MATRIX = [
    ("_Static_assert（c11）", _C11_SRC, "StaticAssertDecl", "c11"),
    ("_Alignof（c11）", "int a = _Alignof(int);\n", "AlignofExpr", "c11"),
    ("_Generic（c11）", "int g = _Generic(x, default: 1);\n", "GenericSelection", "c11"),
    ("_Noreturn（c11）", "_Noreturn void die(void);\n", "NoreturnSpec", "c11"),
    ("_Thread_local（c11）", "_Thread_local int t;\n", "ThreadLocalSpec", "c11"),
    ("static_assert（c23）", _C23_SRC, "StaticAssertC23Decl", "c23"),
    ("nullptr（c23）", "int *p = nullptr;\n", "NullptrLiteral", "c23"),
    ("true（c23）", "int b = true;\n", "BoolLiteral", "c23"),
    ("bool（c23）", "bool f;\n", "BoolType", "c23"),
    ("typeof（c23）", "typeof(int) z;\n", "TypeofSpec", "c23"),
    ("constexpr（c23）", "constexpr int n = 4;\n", "ConstexprSpec", "c23"),
    # 说明符位增量（2026-09-26 批次）——判据同前：从哪一档起解析成插件节点
    ("_Alignas（c11）", "_Alignas(16) char buf[64];\n", "AlignasConstSpec", "c11"),
    ("_Alignas 类型名形态（c11）", "_Alignas(double) char c;\n", "AlignasTypeSpec", "c11"),
    ("_Atomic 限定符（c11）", "_Atomic int x;\n", "AtomicSpec", "c11"),
    ("_Atomic(T)（c11）", "_Atomic(int) x;\n", "AtomicSpec", "c11"),
    ("_Alignas 块作用域（c11）", "void f(void) {\n    _Alignas(16) int x;\n}\n",
     "AlignasConstSpec", "c11"),
    ("_Atomic(T) 块作用域（c11）", "void f(void) {\n    _Atomic(int) x;\n}\n",
     "AtomicSpec", "c11"),
    # c23 小写拼写（同构造异拼写 = c23 侧各写一条同形规则）：从 c23 档起
    ("static_assert 块作用域（c23）", 'void f(void) {\n    static_assert(1, "x");\n}\n',
     "StaticAssertC23Decl", "c23"),
    ("alignas（c23）", "alignas(16) char buf[64];\n", "AlignasC23Spec", "c23"),
    ("alignof（c23）", "int a = alignof(int);\n", "AlignofC23Expr", "c23"),
    ("thread_local（c23）", "thread_local int t;\n", "ThreadLocalC23Spec", "c23"),
    ("_BitInt(N)（c23）", "_BitInt(8) a;\n", "BitIntSpec", "c23"),
    ("_Decimal64（c23）", "_Decimal64 d;\n", "DecimalSpec", "c23"),
    # 十进制浮点**字面量后缀**：词法面的档位判别（基线档 `1.5dd` 被切成两个 token）
    ("_Decimal64 = 1.5dd（c23）", "_Decimal64 e = 1.5dd;\n", "DecimalSpec", "c23"),
]

_TIERS = {
    "baseline": [],
    "c11": ["c11"],
    "c17": ["c11", "c17"],
    "c23": ["c11", "c17", "c23"],
}


def _nodes_with(pack: str, src: str, *, enabled: list[str] | None = None) -> list[str]:
    """按档位加载并解析，返回**递归**节点名（块内形态也看得到）。"""
    ConfigRegistry.load_language(pack, plugins_dir=os.path.join(pack, "plugins"),
                                 enabled=enabled)
    register = GrammarRulesRegister()
    rules = setup_grammar(pack, register)
    stmt = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=pack, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
    )
    lexer = Lexer(rules_dir=pack)
    ast = parser.parse(lexer.tokenize(src))
    return [n.node_name for n in iter_nodes(ast)] if ast is not None else []


def _make_pack(tmp_path, enabled: list[str]) -> str:
    """复制真实包到 tmp，只改 [plugins] enabled 一行（**包内**入口的对照）。"""
    dst = tmp_path / "lang"
    shutil.copytree(_PACK, dst, dirs_exist_ok=True)
    tpc = dst / "tpc.toml"
    text = tpc.read_text(encoding="utf-8")
    text = re.sub(
        r"enabled = \[[^\]]*\]",
        "enabled = [" + ", ".join(f'"{n}"' for n in enabled) + "]",
        text,
    )
    tpc.write_text(text, encoding="utf-8")
    return str(dst)


@pytest.fixture(autouse=True)
def restore_language():
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


class TestThreeTiersInOneProcess:
    """**同一次进程内**依次切四档：每档的接受域各自正确（`enabled=` 覆盖参数）。"""

    @pytest.mark.parametrize(
        "label,src,node,since", _INCREMENT_MATRIX,
        ids=[c[0] for c in _INCREMENT_MATRIX],
    )
    def test_increment_appears_from_its_tier(self, label, src, node, since):
        order = ["baseline", "c11", "c17", "c23"]
        for tier in order:
            names = _nodes_with(_PACK, src, enabled=_TIERS[tier])
            if order.index(tier) < order.index(since):
                assert node not in names, f"{label}：{tier} 档不该有 {node}"
            else:
                assert node in names, f"{label}：{tier} 档缺少 {node}（实得 {sorted(names)}）"

    def test_switching_back_and_forth_is_stable(self):
        """来回切档不串档（缓存键含档位的最直接判据）。"""
        for _ in range(2):
            assert "StaticAssertDecl" in _nodes_with(_PACK, _C11_SRC, enabled=["c11"])
            assert "StaticAssertDecl" not in _nodes_with(_PACK, _C11_SRC, enabled=[])

    def test_none_means_pack_default(self):
        """`enabled=None` = 用包内清单（= c23 全档），不是"沿用上一次"。

        ⚠ 这条语义是刻意选的：`None` 含"用包默认"，否则一个测试把档位切成 c11 之后，
        后续任何 `load_language(pack)` 都会静默停在上一次的档位上。
        """
        assert "StaticAssertC23Decl" in _nodes_with(_PACK, _C23_SRC, enabled=None)

    def test_block_scope_follows_the_tier(self):
        """块作用域同样随档位变（只看文件作用域会漏掉——那条靠 is_statement 全局发现）。"""
        assert "StaticAssertDecl" not in _nodes_with(_PACK, _C11_BLOCK_SRC, enabled=[])
        assert "ExprStmt" in _nodes_with(_PACK, _C11_BLOCK_SRC, enabled=[])
        assert "StaticAssertDecl" in _nodes_with(_PACK, _C11_BLOCK_SRC, enabled=["c11"])


class TestDefaultTierEntry:
    """**包内** `[plugins] enabled` 入口仍成立（pack 副本对照，不重复三档矩阵）。"""

    def test_baseline_tier_has_no_plugin_nodes(self, tmp_path):
        """核心基线档（enabled 为空）：两种静态断言都不是插件节点。

        ⚠ 它们**不是被拒**，而是当普通调用表达式（`ExprStmt`）静默接受——
        判据是"解析成哪个节点"，不是"有没有报错"（见文件头注）。
        """
        pack = _make_pack(tmp_path, [])
        assert "StaticAssertDecl" not in _nodes_with(pack, _C11_SRC)
        assert "StaticAssertC23Decl" not in _nodes_with(pack, _C23_SRC)

    def test_c23_tier_accepts_both(self, tmp_path):
        pack = _make_pack(tmp_path, ["c11", "c17", "c23"])
        assert "StaticAssertDecl" in _nodes_with(pack, _C11_SRC)
        assert "StaticAssertC23Decl" in _nodes_with(pack, _C23_SRC)

    def test_real_pack_meta_matches_c23_tier(self):
        """真实包的启用清单等于最强档（c11+c17+c23）——避免"文档说一套、包里另一套"。"""
        with open(os.path.join(_PACK, "tpc.toml"), "rb") as f:
            enabled = tomllib.load(f)["plugins"]["enabled"]
        assert {"c11", "c17", "c23"} <= set(enabled)

    def test_only_enabled_line_differs(self, tmp_path):
        """两档之间**只差 `enabled` 一行**——"标准 = 启用清单组合"的可机械检查证据。"""
        a = _make_pack(tmp_path / "a", [])
        b = _make_pack(tmp_path / "b", ["c11", "c17", "c23"])
        ta = (pathlib.Path(a) / "tpc.toml").read_text(encoding="utf-8")
        tb = (pathlib.Path(b) / "tpc.toml").read_text(encoding="utf-8")
        diff = [
            (x, y) for x, y in zip(ta.splitlines(), tb.splitlines()) if x != y
        ]
        assert len(diff) == 1, f"两档之间不止 enabled 一行不同：{diff}"
        assert "enabled" in diff[0][0]

    def test_plugin_dirs_identical_across_tiers(self, tmp_path):
        """两档的**插件目录内容完全相同**（同一份资产，差别只在启用清单）。"""
        a = pathlib.Path(_make_pack(tmp_path / "a", []))
        b = pathlib.Path(_make_pack(tmp_path / "b", ["c11", "c17", "c23"]))
        names_a = sorted(p.relative_to(a).as_posix() for p in (a / "plugins").rglob("*.toml"))
        names_b = sorted(p.relative_to(b).as_posix() for p in (b / "plugins").rglob("*.toml"))
        assert names_a == names_b and names_a, "插件目录应一致且非空"


class TestTierCacheHygiene:
    """档位相关的两处缓存陷阱（本轮实测的根因，逐条反向守）。"""

    def test_lexer_follows_recorded_tier_without_extra_param(self):
        """**隐式消费方**（Lexer 走 `resolve`）必须跟随档位，不需要额外参数。

        ⚠ 这是上一轮"改了 enabled 毫无变化"的第二个根因：`_resolve_cache` 的键
        不含档位 ⇒ 同包第二次 resolve 命中上一档的缓存。判据 = 词法里的关键字表。
        """
        ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=["c11"])
        kw_on = Lexer(rules_dir=_PACK).token_define["id"]["keyword"]
        assert "_Static_assert" in kw_on

        ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=[])
        kw_off = Lexer(rules_dir=_PACK).token_define["id"]["keyword"]
        assert "_Static_assert" not in kw_off, "切到基线档后 Lexer 仍带 c11 关键字（缓存串档）"

    def test_entries_source_compares_tier_too(self):
        """`_entries` 来源判据是 (包, 档位)：同包切档必须重新生成声明。

        判据取**声明面差异**：`lexer.token_ext` 由插件声明（包自身 tpc.toml 不含它），
        故 c11 档有、基线档没有——少比档位时第二步会仍留着 c11 的 token_ext。
        """
        ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=["c11"])
        assert ConfigRegistry._entries_enabled == ("c11",)
        assert "lexer.token_ext" in ConfigRegistry._entries, "c11 档应有插件声明的 token_ext"
        src_before = ConfigRegistry._entries_source

        ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=[])
        assert ConfigRegistry._entries_source == src_before, "包没变（只有档位变）"
        assert ConfigRegistry._entries_enabled == (), "档位变了，_entries 必须按新档重建"
        assert "lexer.token_ext" not in ConfigRegistry._entries, (
            "基线档仍留着 c11 的 token_ext 声明（_entries 未按档位重建）"
        )


class TestKeywordFreeIncrementsAreNotTierGated:
    """⚠ **档位的真实边界（2026-09-26 实测，落 `[[属性]]` 时撞上）**：

    档位判别目前靠"**关键字未声明 ⇒ 规则匹配不上**"（插件规则文件本身是**无条件**加载的：
    `setup_grammar` → `load_all_components(<pack>/plugins)`，不看 `enabled`）。
    于是**不依赖任何新关键字的纯语法增量不受档位约束**——`[[属性]]` 就是第一例：
    `[`/`]`/标识符都在核心词法里，规则在基线档照样匹配。

    本类把这个现状**钉住**：若哪天把 `enabled` 升级成"门控一切"（`TODO.md` 的候选语义 ②），
    这条会红——那时应把属性移进真正的档位门控，并把本类改成"基线档不认属性"。
    """

    def test_attributes_parse_even_in_baseline_tier(self):
        names = _nodes_with(_PACK, "[[nodiscard]] int f(void);\n", enabled=[])
        assert "AttributeSpec" in names, names

    def test_keyword_increments_are_gated_by_tokens(self):
        """对照：靠关键字落地的增量在基线档**确实**进不来（档位在它们身上是有效的）。

        判据 = "档位看解析成哪个节点"：基线档下 `bool` / `alignas` 只是标识符。
        """
        for src, node in (("bool f;\n", "BoolType"),
                          ("alignas(16) char c;\n", "AlignasC23Spec"),
                          ("_Atomic(int) x;\n", "AtomicSpec")):
            assert node not in _nodes_with(_PACK, src, enabled=[]), src


class TestEnabledOverrideValidation:
    """`enabled=` 参数的 fail-fast（写错档位必须喊出来）。"""

    @pytest.mark.parametrize(
        "bad",
        ["c11", ["c11", ""], ["c11", 3], ("c11",)],
    )
    def test_invalid_enabled_fails_fast(self, bad):
        with pytest.raises(ConfigError):
            ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=bad)

    def test_declared_list_name_must_resolve(self, tmp_path):
        """包内清单列了不存在的插件名 → fail-fast（拼错名字不许静默少加载）。"""
        pack = _make_pack(tmp_path, ["c11", "no_such_plugin"])
        with pytest.raises(ConfigError) as ei:
            ConfigRegistry.load_language(pack, plugins_dir=os.path.join(pack, "plugins"))
        assert "no_such_plugin" in str(ei.value)
