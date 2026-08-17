"""tests/analyzer/test_name_check.py — semantic_check 插件：task/function 调用名检查。

覆盖通用名称检查（check_name_call 原语）：
    - 定义在前调用 → clean
    - 未定义调用 → W002
    - 前向引用（调用在声明前）→ clean（延迟核对）
    - 跨模块同名 → 隔离正确
"""

import pytest

from core.define import DEFAULT_RULES_DIR, GrammarRulesRegister
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from lexer import Lexer
from analyzer.traversal import AnalysisTraversal


@pytest.fixture(scope="module")
def ctx(config_loaded):
    rules = setup_grammar(DEFAULT_RULES_DIR, GrammarRulesRegister.get_default())
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    rs = RuleSelector(rules, stmt_names)
    parser = Parser(
        rules_dir=DEFAULT_RULES_DIR,
        rules=rules,
        rule_selector=rs,
        log_file="",
    )
    lexer = Lexer(rules_dir=DEFAULT_RULES_DIR)
    return rules, parser, lexer


def _diags(ctx, src):
    """解析 + 语义分析，返回 [(code, level, message)]。"""
    rules, parser, lexer = ctx
    tokens = lexer.tokenize(src)
    ast = parser.parse(tokens)
    assert not parser._parse_truncated, "完整解析应无 truncated"
    at = AnalysisTraversal(rules)
    at.analyze(ast)
    return [(d.code, d.level, d.message) for d in at.diagnostics]


def _codes(diags):
    return sorted(c for c, _, _ in diags)


class TestNameCallCheck:
    """semantic_check 插件：通用名称检查。"""

    def test_defined_call_clean(self, ctx):
        # task/function 定义在前，调用不报
        src = """module m;
  task known_task;
  endtask
  function my_func;
    input x;
    my_func = x;
  endfunction
  always @(*) begin
    known_task;
    a = my_func(1);
  end
endmodule
"""
        assert _diags(ctx, src) == []

    def test_undefined_call_w002(self, ctx):
        # 未定义调用 → W002 warning
        src = """module m;
  always @(*) begin
    bogus_call;
  end
endmodule
"""
        diags = _diags(ctx, src)
        assert ("W002", "warning") in {(c, l) for c, l, _ in diags}
        assert any("bogus_call" in m for _, _, m in diags)

    def test_forward_reference_clean(self, ctx):
        # 前向引用（task 定义在调用之后，Verilog 合法）→ 不误报
        src = """module m;
  always @(*) begin
    fwd_task;
    a = fwd_func(1);
  end
  task fwd_task;
  endtask
  function fwd_func;
    input x;
    fwd_func = x;
  endfunction
endmodule
"""
        assert _diags(ctx, src) == []

    def test_cross_module_isolated(self, ctx):
        # 模块 b 调用模块 a 的 task → 作用域隔离，应报 W002
        src = """module a;
  task t_a;
  endtask
endmodule
module b;
  always @(*) begin
    t_a;
  end
endmodule
"""
        diags = _diags(ctx, src)
        assert ("W002", "warning") in {(c, l) for c, l, _ in diags}

    def test_system_task_not_checked(self, ctx):
        # 系统任务 $display 不参与用户名称检查
        src = """module m;
  always @(*) begin
    $display("x");
  end
endmodule
"""
        assert _diags(ctx, src) == []
