"""formatter 幂等性回归测试。

`format(format(x)) == format(x)`：多次格式化不漂移（行数/内容稳定）。
覆盖所有会改变行数的 pass（端口尾行拆行 / 参数化实例化拆行 / inst_port 拆行）
及缩进/对齐类 pass，防止未来改动引入漂移。
"""

import os
import pytest

from grammar.verilog.plugins.formatter import format_source
from core.define import DEFAULT_RULES_DIR

pytestmark = pytest.mark.usefixtures("config_loaded")


def _fmt(src: str) -> str:
    return format_source(src, DEFAULT_RULES_DIR)


# 特征样本：覆盖每个可能非幂等的 pass
SAMPLES: dict[str, str] = {
    "端口尾行拆行": (
        "module m(\n"
        "    input  [ 7:0] a,\n"
        "    output [ 7:0] b,\n"
        "output [15:0] c );\n"
        "    assign b = a;\n"
        "    assign c = {a, a};\n"
        "endmodule\n"
    ),
    "参数化实例化拆行": (
        "module m;\n"
        "    foo #(.A(a),\n"
        "        .B(b)) inst_name (\n"
        "        .clk(clk),\n"
        "        .rst(rst)\n"
        "    );\n"
        "endmodule\n"
    ),
    "inst_port 拆行": (
        "module m;\n"
        "    foo u0 (.clk(clk), .rst(rst), .en(en));\n"
        "endmodule\n"
    ),
    "ifdef 悬挂": (
        "module m;\n"
        "    always @* begin\n"
        "        if (x)\n"
        "`ifdef F\n"
        "            y = 1;\n"
        "`else\n"
        "            y = 0;\n"
        "`endif\n"
        "    end\n"
        "endmodule\n"
    ),
    "三目链续行": (
        "module m;\n"
        "`ifdef ALTOPS\n"
        "    assign pcpi_rd =\n"
        "        instr_mul ? (a + b) :\n"
        "        instr_mulh ? (a - b) : 1'b0;\n"
        "`endif\n"
        "endmodule\n"
    ),
    "声明多行续行": (
        "module m;\n"
        "    reg a,\n"
        "        b,\n"
        "        c;\n"
        "endmodule\n"
    ),
    "端口列对齐": (
        "module m(\n"
        "    input clk,\n"
        "    output reg [31:0] mem_addr,\n"
        "    input [31:0] mem_rdata,\n"
        "    output [3:0] mem_wstrb\n"
        ");\n"
        "endmodule\n"
    ),
}


@pytest.mark.parametrize("name", list(SAMPLES))
def test_format_idempotent_samples(name: str):
    """特征样本：format(format(x)) == format(x)，行数稳定。"""
    src = SAMPLES[name]
    once = _fmt(src)
    twice = _fmt(once)
    assert twice == once, f"{name}: 二次格式化漂移"
    assert len(twice.splitlines()) == len(once.splitlines()), f"{name}: 行数漂移"


def test_format_idempotent_picorv32():
    """PicoRV32 全文件：二次格式化稳定（黄金基准，防止行数/content 漂移）。"""
    real = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "e2e", "samples", "real", "gen", "gen_picorv32.v",
    )
    if not os.path.exists(real):
        pytest.skip("PicoRV32 sample not present")
    with open(real, encoding="utf-8") as f:
        src = f.read()
    once = _fmt(src)
    twice = _fmt(once)
    assert twice == once, "PicoRV32 二次格式化漂移"
