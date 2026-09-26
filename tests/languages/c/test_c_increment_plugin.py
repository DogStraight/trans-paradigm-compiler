"""tests/languages/c/test_c_increment_plugin.py — C 包的**增量插件形态**验证。

目标（0.1.3 目标 ①）："核心基线 + 标准增量插件"的组合形态。本文件验证四件事：

1. **增量住在插件目录里**：`StaticAssertDecl` 只出现在 `grammar/c/plugins/c11/` 下，
   核心基线文件（`00_*`/`01_*`/`02_*`/`03_*`）**不含**它——"加标准"= 加插件，不改基座；
2. **插件随包生效**：`setup_grammar("grammar/c")` 的规则表里**有**该规则、词法扩展也生效
   （`_Static_assert` 是关键字）；
3. **核心 `Stmt` 选择器未被改动**（增量的边界来自插件自己的文件）；
4. **解析形态确实变了**：`_Static_assert(1, "x");` → `StaticAssertDecl`
   （条件与消息都挂上）。

**启用入口（本轮实测更正）**：语言包 `tpc.toml` 的 `[plugins] enabled` 就是
**运行时启用清单**——它决定哪些插件目录的声明被合并（含 `[lexer] token_ext`）。
⚠ 上一轮我把这份清单当成"打包/分发面装饰"，**是错的**：加它之前 `_Static_assert`
一直是标识符；加上后立刻成为关键字。故 ROADMAP 说的"启用组合等效某标准"**在运行时
可表达**（改这份清单即可）；差异只在"同一次进程内切两档"需要重载或 pack 副本。
"""

import os
from pathlib import Path

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector

ROOT_DIR = Path(__file__).resolve().parents[3]
_PACK = "grammar/c"
_PLUGINS = os.path.join(_PACK, "plugins")
_SRC = '_Static_assert(sizeof(int) > 0, "int must be non-empty");\n'

# 该样本不依赖 sizeof 的规则（本包尚未做 sizeof）——用最小可用条件
_SRC_MIN = '_Static_assert(1, "always true");\n'


def _load():
    """加载 C 包 + 其 plugins/。

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
    return rules, (lambda src: parser.parse(lexer.tokenize(src)))


@pytest.fixture
def restore_language():
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _names(ast) -> list[str]:
    return [n.node_name for n in (getattr(ast, "sub_node", []) or [])]


class TestPluginIsLoadedWithPack:
    def test_rule_present(self, restore_language):
        rules, _ = _load()
        assert "StaticAssertDecl" in rules

    def test_construct_parses_into_plugin_node(self, restore_language):
        """`_Static_assert(1, "x");` → 插件的 `StaticAssertDecl`。

        ⚠ **接通条件（本轮实测得出，勿再按"打包面"理解）**：插件必须在语言包
        `tpc.toml` 的 `[plugins] enabled` 清单里 —— 那份清单是**运行时启用清单**，
        `load_language(pack, plugins_dir=…)` 只在被列出的插件上合并声明（含
        `[lexer] token_ext` 的词法扩展）。对照证据：verilog 的 `nand`（plugin 关键字）
        在 verilog 下**无需任何 ext_dirs** 即为关键字，因为 verilog 的 `enabled`
        列了 gates。
        """
        _, parse = _load()
        ast = parse(_SRC_MIN)
        assert _names(ast) == ["StaticAssertDecl"], _names(ast)

    def test_condition_and_message_are_bound(self, restore_language):
        _, parse = _load()
        ast = parse(_SRC_MIN)
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


class TestIncrementDoesNotTouchBaseline:
    def test_core_stmt_selector_untouched_by_plugin(self, restore_language):
        """增量插件**不改基座**：核心 `Stmt` 选择器里没有增量规则。

        （这也是本插件只支持文件作用域的原因——块作用域要在核心 `Stmt` 选择器里加
        分支，属跨文件改动，留待"注入机制补『改』路径"立项后处理。）
        """
        rules, _ = _load()
        stmt = rules["Stmt"]
        prods = getattr(stmt, "production", [])
        joined = " ".join(prods)
        assert "StaticAssertDecl" not in joined
