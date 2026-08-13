"""SystemVerilog 基础覆盖测试（P1.3）。

验证 logic 声明/端口 + always_ff/always_comb 能 parse + format。
"""

import pytest

from grammar.verilog.plugins.formatter import format_source
from core.define import DEFAULT_RULES_DIR

pytestmark = pytest.mark.usefixtures("config_loaded")


SV_SRC = """module sv_test(
    input logic clk,
    input logic rst_n
);
    logic [7:0] data;
    logic valid;

    always_ff @(posedge clk) begin
        if (!rst_n)
            data <= 8'h00;
        else
            data <= data + 1;
    end

    always_comb begin
        valid = data != 8'h00;
    end
endmodule
"""


def _fmt(src: str) -> str:
    return format_source(src, DEFAULT_RULES_DIR)


class TestSVBasic:
    def test_logic_port(self):
        """input logic clk → 端口带 logic 类型。"""
        out = _fmt(SV_SRC)
        assert "input logic  clk," in out

    def test_logic_decl(self):
        """logic [7:0] data → logic 声明保留。"""
        out = _fmt(SV_SRC)
        assert "logic [7:0] data;" in out
        assert "logic valid;" in out

    def test_always_ff(self):
        """always_ff @(posedge clk) → 关键字保留 + 块结构。"""
        out = _fmt(SV_SRC)
        assert "always_ff @(posedge clk) begin" in out
        assert "data <= 8'h00;" in out

    def test_always_comb(self):
        """always_comb begin → 关键字保留。"""
        out = _fmt(SV_SRC)
        assert "always_comb begin" in out
        assert "valid = data != 8'h00;" in out

    def test_idempotent(self):
        """SV 输出幂等。"""
        out = _fmt(SV_SRC)
        assert _fmt(out) == out

    def test_token_complete(self):
        """SV 格式化 token 完整。"""
        out = _fmt(SV_SRC)

        def strip_all(text: str) -> str:
            lines = []
            for line in text.splitlines():
                ci = line.find("//")
                if ci >= 0:
                    line = line[:ci]
                lines.append(line)
            return "".join("".join(lines).split())

        assert strip_all(out) == strip_all(SV_SRC)
