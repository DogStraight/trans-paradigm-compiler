"""增强语法渲染 + 管线展开开关（P1.4）测试。

验证：
  1. renderer 增强节点 layout：TypedPortDecl/TypeDecl 等不经过 transform 也能直出
     （保留增强语法源码路径）
  2. 管线 expand_enhanced 开关：True 展开增强节点（当前默认），False 保留增强语法
  3. 展开路径产出基础 Verilog（token 与保留路径的增强语法不对应，但各自完整）
"""

import os

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")

# 增强语法样本（typed_ports）：模块端口用类型引用 + type 定义
ENHANCED_SRC = """module spi_invoker(
    input clk,
    input rstn,
    spi.slave spi_io
);
endmodule

type spi {
    master : input clk, input miso, output mosi, output cs;
    slave  : input clk, input mosi, output miso, output cs;
}
"""


def _run(**kw):
    return run_pipeline_on_source(
        source=ENHANCED_SRC, quiet=True, no_lint=True, **kw
    )


def test_expand_path_emits_basic_verilog():
    """展开路径（默认）：增强端口展开为基础端口声明，type 定义被消费。"""
    r = _run()
    assert r["success"], r.get("error", "")
    out = r["output"]
    # 展开产物：spi.slave → 具体端口（类型名_端口名）
    assert "input    spi_io_clk" in out
    assert "output   spi_io_miso" in out
    # type 定义不保留（展开路径消费掉）
    assert "type spi" not in out


def test_preserve_path_keeps_enhanced_syntax():
    """保留路径（expand_enhanced=False）：增强语法原样渲染，不展开。"""
    r = _run(expand_enhanced=False)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # 类型端口保留
    assert "spi.slave spi_io" in out
    # type 定义保留
    assert "type spi" in out
    assert "master : input clk, input miso, output mosi, output cs;" in out
    assert "slave : input clk, input mosi, output miso, output cs;" in out
    # 不出现展开产物
    assert "spi_io_clk" not in out


def test_preserve_path_token_complete():
    """保留路径：增强语法 token 完整（去空白后与输入一致）。"""
    r = _run(expand_enhanced=False)
    assert r["success"]
    out = r["output"]

    def strip_all(text: str) -> str:
        lines = []
        for line in text.splitlines():
            ci = line.find("//")
            if ci >= 0:
                line = line[:ci]
            lines.append(line)
        return "".join("".join(lines).split())

    assert strip_all(out) == strip_all(ENHANCED_SRC)


def test_expand_path_format_idempotent():
    """展开路径输出经 format 后幂等（formatter 服务两条路）。"""
    r = _run()
    assert r["success"]
    from grammar.verilog.plugins.formatter import format_source
    from core.define import DEFAULT_RULES_DIR
    once = format_source(r["output"], DEFAULT_RULES_DIR)
    twice = format_source(once, DEFAULT_RULES_DIR)
    assert twice == once
