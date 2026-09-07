"""tests/languages/verilog/test_typed_ports.py — typed_ports 展开路径端口位宽（packed_range）携带。

覆盖 TODO P1.5 "role 端口 packed_range 携带（接口位宽闭环）"：
    - 直接引用类型端口（spi.slave spi_io）展开后保留 [7:0]
    - 范围引用类型参数（[DATA_WIDTH-1:0]）字面透传
    - invert 引用（slave : invert master）展开后方向反转且位宽保留
    - 嵌套类型引用（spi.master inner）展开后位宽随前缀透传
    - wrapper 模块（impl [role] (...)）的 role 派生端口保留位宽
    - 无位宽端口不产生空 [] 残片；保留路径（expand_enhanced=False）不受影响
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


RANGED_SRC = """module top(
    input clk,
    spi.slave spi_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : input clk, input [7:0] mosi, output cs;
}
"""


def _run(src=RANGED_SRC, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


def test_ranged_role_port_expands_with_width():
    """直接引用：role 端口声明的 [7:0] 在展开路径保留。"""
    r = _run()
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "[7:0] spi_io_mosi" in out
    assert "spi_io_clk" in out
    # 无位宽端口不带空 [] 残片
    assert "[]" not in out
    assert "type spi" not in out


def test_preserve_path_keeps_ranged_role_ports():
    """保留路径：增强语法原样渲染，role 端口位宽保留在源文本。"""
    r = _run(expand_enhanced=False)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "spi.slave spi_io" in out
    assert "master : input clk, output [7:0] mosi, output cs;" in out
    assert "slave : input clk, input [7:0] mosi, output cs;" in out


PARAM_RANGE_SRC = """module top(
    input clk,
    spi.slave spi_io
);
endmodule

type spi (parameter DATA_WIDTH = 8) {
    master : input clk, output [DATA_WIDTH-1:0] mosi, output cs;
    slave  : input clk, input [DATA_WIDTH-1:0] mosi, output cs;
}
"""


def test_param_referenced_range_expands_literal():
    """范围引用类型参数（[DATA_WIDTH-1:0]）：展开时字面透传（BinaryOp 重建）。"""
    r = _run(src=PARAM_RANGE_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # BinaryOp 渲染器在运算符两侧加空格（引擎约定，与普通端口渲染一致）
    assert "input   [DATA_WIDTH - 1:0] spi_io_mosi" in out


INVERT_SRC = """module top(
    input clk,
    spi.slave spi_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : invert master;
}
"""


def test_simple_invert_keeps_range():
    """invert 引用：方向反转（output→input）且位宽保留。"""
    r = _run(src=INVERT_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # master 的 mosi 是 output [7:0] → slave 反转后为 input [7:0]
    assert "[7:0] spi_io_mosi" in out
    # master 的 clk 是 input → slave 反转后为 output（行内方向应为 output）
    clk_line = next((ln for ln in out.splitlines() if "spi_io_clk" in ln), "")
    assert clk_line.strip().startswith("output")


NESTED_SRC = """module top(
    input clk,
    wrap.slave w_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : input clk, input [7:0] mosi, output cs;
}

type wrap {
    master : spi.master inner, input enable;
    slave  : spi.slave inner;
}
"""


def test_nested_type_carries_range():
    """嵌套类型引用：位宽随前缀端口透传（w_io_inner_mosi 保留 [7:0]）。"""
    r = _run(src=NESTED_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "input   [7:0] w_io_inner_mosi" in out
    assert "w_io_inner_clk" in out
    assert "w_io_inner_cs" in out
    assert "type wrap" not in out


WRAPPER_SRC = """module top(
    input clk,
    spi.master spi_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi;
    impl [master] (
        input clk
    ) {
        wire [7:0] data;
    }
}
"""


def test_wrapper_module_ports_keep_range():
    """wrapper 模块（impl [role]）的 role 派生端口保留位宽。"""
    r = _run(src=WRAPPER_SRC)
    assert r["success"], r.get("error", "")
    main = r["output"]
    assert "output  [7:0] spi_io_mosi" in main
    extra = dict(r.get("extra_outputs", []))
    assert "spi_master" in extra
    assert "output [7:0] mosi" in extra["spi_master"]


NO_RANGE_SRC = """module top(
    input clk,
    spi.slave spi_io
);
endmodule

type spi {
    master : input clk, output mosi;
    slave  : input clk, input mosi;
}
"""


def test_no_range_ports_have_no_empty_brackets():
    """无位宽端口：不产生空 [] 残片，端口正常展开。"""
    r = _run(src=NO_RANGE_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "[]" not in out
    assert "spi_io_mosi" in out
    assert "spi_io_clk" in out


NESTED_INVERT_SRC = """module top(
    input clk,
    wrap.slave w_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : input clk, input [7:0] mosi, output cs;
}

type wrap {
    master : spi.master inner, input enable;
    slave  : spi.slave inner, invert master;
}
"""


def test_nested_invert_no_skip_leak():
    """nested+invert 组合：展开不再泄漏字面 SKIP（L1 防御）。

    映射表过滤空行（嵌套引用 dict 拍平残留）+ expand 端过滤无产出结果。
    诚实边界（TODO P1.5 遗留）：invert 对含嵌套引用的 role，其嵌套展开
    端口（inner_* 方向反转）仍不参与反转——本测试只保证不泄漏 SKIP，
    不断言 invert 部分的 inner_* 展开完整。
    """
    r = _run(src=NESTED_INVERT_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "SKIP" not in out
    assert "w_io_inner_mosi" in out
    assert "w_io_enable" in out
