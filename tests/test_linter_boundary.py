"""Linter 边界检查（P1）单元测试 — block.start/block.end 配对。"""

import pytest
from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS


@pytest.fixture(scope="session")
def scanner(config_loaded):
    """已配置的 LinterScanner 实例（只开 P1）。"""
    from linter.scanner import LinterScanner

    ls = LinterScanner(
        DEFAULT_RULES_DIR,
        ext_dirs=DEFAULT_EXT_DIRS,
    )
    ls.enable_phase1 = True
    ls.enable_phase2 = False
    ls.enable_phase3 = False
    return ls


def _err_msgs(errs):
    """提取错误消息列表，方便断言。"""
    return [e.message for e in errs]


# ═══════════════════════════════════════════════════════
# 正常（不应报错）
# ═══════════════════════════════════════════════════════


class TestNormalBoundary:
    """合法 Verilog 块结构不应产生 P1 错误。"""

    def test_empty_module(self, scanner):
        errs = scanner.scan("module m; endmodule")
        assert len(errs) == 0

    def test_module_with_body(self, scanner):
        src = """
module test;
    wire a;
    assign b = a;
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_nested_begin_end(self, scanner):
        src = """
module test;
    always @(*) begin
        a = 1;
    end
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_double_begin_end(self, scanner):
        src = """
module test;
    always @(*) begin
        if (x) begin
            a = 1;
        end
    end
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_function_block(self, scanner):
        src = """
module test;
    function foo;
        input clk;
    endfunction
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_task_block(self, scanner):
        src = """
module test;
    task bar;
        input a;
    endtask
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_generate_block(self, scanner):
        src = """
module test;
    generate
        if (GEN) begin
            wire a;
        end
    endgenerate
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_old_style_function(self, scanner):
        src = """
module test;
    function foo;
        input clk;
        reg data;
    endfunction
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_ansi_function(self, scanner):
        src = """
module test;
    function automatic [7:0] foo(input clk);
        foo = clk;
    endfunction
endmodule
"""
        assert len(scanner.scan(src)) == 0


# ═══════════════════════════════════════════════════════
# 缺少关闭符
# ═══════════════════════════════════════════════════════


class TestMissingCloser:
    """块有开始无结束。"""

    def test_missing_endmodule(self, scanner):
        errs = scanner.scan("module m;")
        assert len(errs) == 1
        assert "unclosed" in errs[0].message

    def test_missing_end_for_begin(self, scanner):
        src = """
module test;
    always @(*) begin
        a = 1;
endmodule
"""
        errs = scanner.scan(src)
        # endmodule 是类型错误的关闭符（endmodule for begin），不计为 missing
        # 栈中剩下 begin 未关闭
        unclosed = [e for e in errs if "unclosed" in e.message]
        assert len(unclosed) == 1

    def test_missing_endfunction(self, scanner):
        src = """
module test;
    function foo;
        input clk;
endmodule
"""
        errs = scanner.scan(src)
        unclosed = [e for e in errs if "unclosed" in e.message]
        assert len(unclosed) == 1


# ═══════════════════════════════════════════════════════
# 多余关闭符
# ═══════════════════════════════════════════════════════


class TestExtraCloser:
    """无对应开始的结束符。"""

    def test_stray_endmodule(self, scanner):
        errs = scanner.scan("endmodule")
        assert len(errs) == 1
        assert "unmatched" in errs[0].message

    def test_extra_end(self, scanner):
        src = """
module test;
    wire a;
end
endmodule
"""
        errs = scanner.scan(src)
        # end 不匹配 module → mismatched，然后 endmodule 是多余的
        msgs = _err_msgs(errs)
        assert any("mismatched" in m for m in msgs)
        assert any("unmatched" in m for m in msgs)


# ═══════════════════════════════════════════════════════
# 错误类型关闭符
# ═══════════════════════════════════════════════════════


class TestWrongCloserType:
    """关闭符类型与上一个开启符不匹配。"""

    def test_endmodule_closes_begin(self, scanner):
        src = """
module test;
    always @(*) begin
        a = 1;
    endmodule
    end
"""
        errs = scanner.scan(src)
        # endmodule 不匹配 begin → mismatched，end 也不匹配 module
        msgs = _err_msgs(errs)
        assert sum("mismatched" in m for m in msgs) == 2

    def test_end_closes_module(self, scanner):
        src = """
module test;
    wire a;
end
endmodule
"""
        errs = scanner.scan(src)
        msgs = _err_msgs(errs)
        assert any("mismatched" in m for m in msgs)

    def test_endfunction_closes_module(self, scanner):
        src = """
module test;
    wire a;
endfunction
endmodule
"""
        errs = scanner.scan(src)
        msgs = _err_msgs(errs)
        assert any("mismatched" in m for m in msgs)

    def test_endtask_closes_begin(self, scanner):
        src = """
module test;
    always @(*) begin
        a = 1;
    endtask
end
endmodule
"""
        errs = scanner.scan(src)
        msgs = _err_msgs(errs)
        assert any("mismatched" in m for m in msgs)


# ═══════════════════════════════════════════════════════
# 多模块
# ═══════════════════════════════════════════════════════


class TestMultipleModules:
    """一个文件中多个模块。"""

    def test_two_separate_modules(self, scanner):
        src = """
module a;
endmodule
module b;
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_module_within_module_missing_end(self, scanner):
        src = """
module a;
    wire x;
module b;
    wire y;
endmodule
"""
        errs = scanner.scan(src)
        unclosed = [e for e in errs if "unclosed" in e.message]
        assert len(unclosed) == 1


# ═══════════════════════════════════════════════════════
# 括号边界 ( )
# ═══════════════════════════════════════════════════════


class TestParenBoundary:
    """括号 ( ) 边界配对。"""

    def test_normal_port_parens(self, scanner):
        src = """
module test (
    input clk,
    output data
);
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_normal_always_sensitivity(self, scanner):
        src = """
module test;
    always @(posedge clk) begin
        a <= b;
    end
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_missing_rparen(self, scanner):
        src = """
module test (
    input clk,
    output data
;
endmodule
"""
        errs = scanner.scan(src)
        assert any("unclosed" in e.message for e in errs)

    def test_extra_rparen(self, scanner):
        src = """
module test;
    always @(posedge clk) begin
        a <= b;
    end)
endmodule
"""
        errs = scanner.scan(src)
        assert any("mismatched" in e.message or "unmatched" in e.message for e in errs)

    def test_rparen_before_lparen(self, scanner):
        """反向：) 在 ( 之前出现"""
        src = """
module test;
    assign a = b);
endmodule
"""
        errs = scanner.scan(src)
        assert any("unmatched" in e.message or "mismatched" in e.message for e in errs)

    def test_normal_param_list(self, scanner):
        src = """
module test #(parameter W=8) (
    input [W-1:0] data
);
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_param_list_missing_rparen(self, scanner):
        """反向：参数列表缺 ) — ) 真正缺失"""
        src = """
module test #(parameter W=8
    input clk
endmodule
"""
        errs = scanner.scan(src)
        assert any("unclosed" in e.message for e in errs)


# ═══════════════════════════════════════════════════════
# 方括号边界 [ ]
# ═══════════════════════════════════════════════════════


class TestBracketBoundary:
    """方括号 [ ] 边界配对。"""

    def test_normal_range(self, scanner):
        src = """
module test;
    reg [7:0] data;
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_missing_rbracket(self, scanner):
        src = """
module test;
    reg [7:0 data;
endmodule
"""
        errs = scanner.scan(src)
        assert any("unclosed" in e.message for e in errs)

    def test_extra_rbracket(self, scanner):
        src = """
module test;
    reg [7:0] data];
endmodule
"""
        errs = scanner.scan(src)
        assert any("mismatched" in e.message or "unmatched" in e.message for e in errs)

    def test_rbracket_before_lbracket(self, scanner):
        """反向：] 在 [ 之前出现"""
        src = """
module test;
    assign a = b];
endmodule
"""
        errs = scanner.scan(src)
        assert any("unmatched" in e.message or "mismatched" in e.message for e in errs)

    def test_nested_range_in_port(self, scanner):
        src = """
module test (
    input [7:0] data
);
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_function_with_range(self, scanner):
        src = """
module test;
    function [7:0] foo;
        foo = 0;
    endfunction
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_multiple_ranges(self, scanner):
        """正向：多条声明含 range"""
        src = """
module test;
    reg [3:0] a, [7:0] b;
endmodule
"""
        assert len(scanner.scan(src)) == 0


# ═══════════════════════════════════════════════════════
# Generate 边界
# ═══════════════════════════════════════════════════════


class TestGenerateBoundary:
    """generate/endgenerate 边界配对。"""

    def test_normal_generate(self, scanner):
        src = """
module test;
    generate
        if (GEN) begin
            wire a;
        end
    endgenerate
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_missing_endgenerate(self, scanner):
        """反向：缺 endgenerate"""
        src = """
module test;
    generate
        if (GEN) begin
            wire a;
        end
endmodule
"""
        errs = scanner.scan(src)
        assert any("unclosed" in e.message for e in errs)

    def test_extra_endgenerate(self, scanner):
        """反向：多余的 endgenerate"""
        src = """
module test;
    generate
        wire a;
    endgenerate
    endgenerate
endmodule
"""
        errs = scanner.scan(src)
        assert any("mismatched" in e.message or "unmatched" in e.message for e in errs)


# ═══════════════════════════════════════════════════════
# Task 边界
# ═══════════════════════════════════════════════════════


class TestTaskBoundary:
    """task/endtask 边界配对。"""

    def test_normal_task(self, scanner):
        src = """
module test;
    task bar;
        input a;
    endtask
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_missing_endtask(self, scanner):
        """反向：缺 endtask"""
        src = """
module test;
    task bar;
        input a;
endmodule
"""
        errs = scanner.scan(src)
        assert any("unclosed" in e.message for e in errs)

    def test_extra_endtask(self, scanner):
        """反向：多余的 endtask"""
        src = """
module test;
    task bar;
        input a;
    endtask
    endtask
endmodule
"""
        errs = scanner.scan(src)
        assert any("mismatched" in e.message or "unmatched" in e.message for e in errs)


# ═══════════════════════════════════════════════════════
# 跨类型错误关闭符
# ═══════════════════════════════════════════════════════


class TestCrossTypeWrongCloser:
    """不同类型的关闭符相互错误匹配。"""

    def test_endtask_closes_function(self, scanner):
        src = """
module test;
    function foo;
        input clk;
    endtask
endfunction
endmodule
"""
        errs = scanner.scan(src)
        msgs = _err_msgs(errs)
        assert any("mismatched" in m for m in msgs)

    def test_endgenerate_closes_begin(self, scanner):
        src = """
module test;
    always @(*) begin
        a = 1;
    endgenerate
end
endmodule
"""
        errs = scanner.scan(src)
        msgs = _err_msgs(errs)
        assert any("mismatched" in m for m in msgs)

    def test_rbracket_closes_lparen(self, scanner):
        """反向：] 关闭 ("""
        src = """
module test (
    input [7:0] data
];
endmodule
"""
        errs = scanner.scan(src)
        msgs = _err_msgs(errs)
        assert any("mismatched" in m for m in msgs)


# ═══════════════════════════════════════════════════════
# 混合边界嵌套
# ═══════════════════════════════════════════════════════


class TestMixedBoundary:
    """关键字块 + 括号 + 方括号混合嵌套。"""

    def test_all_boundaries(self, scanner):
        """正向：所有边界正确嵌套"""
        src = """
module test #(parameter W=8) (
    input [W-1:0] a,
    output reg [W-1:0] b
);
    function [3:0] add(input [3:0] x, y);
        add = x + y;
    endfunction
    generate
        if (W > 1) begin
            assign b = a;
        end
    endgenerate
endmodule
"""
        assert len(scanner.scan(src)) == 0

    def test_missing_bracket_in_paren(self, scanner):
        """反向：缺 ] 在 ( 内引发级联"""
        src = """
module test (
    input [7:0 data,
    output reg result
);
endmodule
"""
        errs = scanner.scan(src)
        assert any("unclosed" in e.message for e in errs)

    def test_deep_nested_all_types(self, scanner):
        """正向：深层嵌套 — module > generate > begin > function > range"""
        src = """
module test;
    generate
        if (1) begin
            function [3:0] map;
                map = 0;
            endfunction
        end
    endgenerate
endmodule
"""
        assert len(scanner.scan(src)) == 0

