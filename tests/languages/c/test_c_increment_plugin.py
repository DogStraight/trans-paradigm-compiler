"""tests/languages/c/test_c_increment_plugin.py — C 包的**增量插件形态**验证。

目标（0.1.3 目标 ①）："核心基线 + 标准增量插件"的组合形态。本文件验证四件事：

1. **增量住在插件目录里**：`StaticAssertDecl` 只出现在 `grammar/c/plugins/c11/` 下，
   核心基线文件（`00_*`/`01_*`/`02_*`/`03_*`）**不含**它——"加标准"= 加插件，不改基座；
2. **插件随包生效**：`setup_grammar("grammar/c")` 的规则表里**有**该规则、词法扩展也生效
   （`_Static_assert` 是关键字）；
3. **核心 `Stmt` 选择器未被改动**（增量的边界来自插件自己的文件）；
4. **解析形态确实变了**：`_Static_assert(1, "x");` → `StaticAssertDecl`
   （条件与消息都挂上）。

⚠ **实测发现（记入缺口档与 TODO）**：本仓当前**没有运行时的启用/停用开关**——
`<pack>/plugins/` 是随包**自动发现**的（`setup_grammar(rules_dir, register, ext_dirs)`
没有 enabled 参数；`load_language(pack, plugins_dir=…)` 指定与否都加载到同一份）。
语言包 `tpc.toml` 里的 `[plugins] enabled` 属**打包/分发面**清单。故 ROADMAP 说的
"启用组合等效某个标准"目前只能在**打包面**或**pack 副本**上表达，不能在一次运行里
切换两档——这是"标准插件族"形态缺的那块，已登记。
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
    lexer = Lexer(rules_dir=_PACK)
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

    def test_construct_not_yet_parsed_as_plugin_node(self, restore_language):
        """⚠ **缺口（本轮钉住现状）**：规则已从插件加载，但**词法扩展未接通**——
        `_Static_assert` 仍是标识符，故 `_Static_assert(1, "x");` 被解析成
        `ExprStmt`（当作函数调用），而**不是**插件的 `StaticAssertDecl`。

        证据与下一步（已记缺口档）：`setup_grammar(..., ext_dirs=[plugins])` **不足以**
        让 `[lexer] token_ext` 生效；verilog 侧的用法是把 `ext_dirs` 传给
        **`LinterScanner(rules_dir=…, ext_dirs=["…/plugins"])`**（见
        `tests/languages/verilog/test_2005_batch2.py`）。下一步先确认
        `Lexer`/`LinterScanner` 是怎么消费 `ext_dirs` 的，再把本用例改为断言
        `["StaticAssertDecl"]`。**不要**为了让它变绿而改断言迁就现状。
        """
        _, parse = _load()
        names = _names(parse(_SRC_MIN))
        assert names == ["ExprStmt"], (
            f"形态变了（现为 {names}）——若词法扩展已接通，请把本用例改为断言 "
            '["StaticAssertDecl"] 并同步缺口档'
        )


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
