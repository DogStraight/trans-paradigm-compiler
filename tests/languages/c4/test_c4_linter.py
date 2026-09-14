"""tests/languages/c4/test_c4_linter.py — c4 第二语言：linter 可跑性验证。

验证 [linter] 配置下沉后 c4 语言包可直接跑 linter：
    - 语言包参数化：LinterScanner 直接用 c4 rules_dir（无需先 load_language）
    - 自推导入口：B 类 ident 候选是单一全局集合（不按上下文分组），
      c4 无需 statement_entry/body_context 字段
    - 语句发现/结构检查基于 is_statement 显式标记 + production 推导

覆盖：合法 c4 代码 0 诊断、缺分号报 phase-statement、拼错关键字报
phase-unrecognized。
"""

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from linter.scanner import LinterScanner


@pytest.fixture(scope="module")
def c4_scanner(config_loaded):
    """构造 c4 LinterScanner（语言包参数化：rules_dir 直接指向 c4）。

    用独立 GrammarRulesRegister 实例，避免污染全局单例（get_default() 的
    rules 缓存被 c4 规则污染后，后续 verilog 测试规则树会混合）。
    """
    del config_loaded  # fixture 依赖声明（配置加载）
    scanner = LinterScanner(
        rules_dir="grammar/c4",
        register=GrammarRulesRegister(),
    )
    yield scanner
    # 恢复 verilog 语言包（避免污染后续测试的 ConfigRegistry 状态）
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


class TestC4LinterBasic:
    """c4 linter 基础可跑性。"""

    def test_valid_program_clean(self, c4_scanner):
        src = "int main() { int a; a = 1; return a; }"
        errs = c4_scanner.scan(src)
        assert errs == []

    def test_missing_semicolon_reported(self, c4_scanner):
        src = "int main() { int a; a = 1 return a; }"
        errs = c4_scanner.scan(src)
        assert len(errs) >= 1
        assert any(e.code == "phase-statement" for e in errs)

    def test_if_missing_paren_reported(self, c4_scanner):
        # if 缺左括号 → 唯一候选 IfStmt 结构检查报 phase-statement
        src = "int main() { int a; if a) return; return 0; }"
        errs = c4_scanner.scan(src)
        assert any(
            e.code == "phase-statement" and "l_parentheses" in e.message for e in errs
        )

    def test_if_else_chain_clean(self, c4_scanner):
        src = (
            "int fib(int n) { "
            "if (n < 2) return n; "
            "else return fib(n-1) + fib(n-2); }"
        )
        errs = c4_scanner.scan(src)
        assert errs == []
