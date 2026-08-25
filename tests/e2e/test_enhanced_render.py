"""增强语法渲染 + 管线展开开关（P1.4）测试。

验证：
  1. renderer 增强节点 layout：TypedPortDecl/TypeDecl/TypeImplDecl/impl 绑定
     不经过 transform 也能直出（保留增强语法源码路径）
  2. 管线 expand_enhanced 开关：True 展开增强节点（当前默认），False 保留增强语法
  3. 保留路径 token 完整；保留路径默认不 format（formatter 不识别增强结构）
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")

# 增强语法样本（typed_ports）：模块端口用类型引用 + type 定义 + impl 绑定 + TypeImplDecl
ENHANCED_SRC = """module top(
    input clk,
    spi.slave spi_io
);
    spi_master u0 (.clk(clk));
    impl spi.master (.clk(clk)) => top;
endmodule

type spi {
    master : input clk, input miso, output mosi, output cs;
    slave  : input clk, input mosi, output miso, output cs;
    impl [master] (
        input clk,
        output sck
    ) {
        wire [7:0] data;
    }
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
    # impl 绑定保留（括号 + `=>` 箭头）
    assert "impl spi.master (.clk(clk)) => top;" in out
    # TypeImplDecl 保留（body 内容渲染）
    assert "impl [master] ( input clk, output sck) {" in out
    assert "wire [7:0] data;" in out
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


def test_preserve_path_format_enhanced():
    """保留路径默认过 formatter：增强语法 curly 块缩进正确（boundary 支持花括号）。"""
    r = _run(expand_enhanced=False)
    assert r["success"]
    out = r["output"]
    # TypeImplDecl body 内容渲染
    assert "wire [7:0] data;" in out
    # curly 块缩进：type body 内容 4 空格、TypeImplDecl body 内容 8 空格
    assert "    master : input clk, input miso, output mosi, output cs;" in out
    assert "        wire [7:0] data;" in out


# ── nested / invert 补充验证（P1.4）──

NESTED_SRC = """module top(
    input clk,
    spi.slave spi_io
);
    impl spi.master (.clk(clk)) => top;
endmodule

type spi {
    master : input clk, input miso, output mosi, output cs;
    slave  : input clk, input mosi, output miso, output cs;
}

type wrap {
    master : spi.master inner, input enable;
    slave  : spi.slave inner, invert master;
}
"""


def _run_nested(**kw):
    return run_pipeline_on_source(
        source=NESTED_SRC, quiet=True, no_lint=True, **kw
    )


def test_nested_preserve_renders_nested_port():
    """保留路径：嵌套类型端口（spi.master inner）渲染。"""
    r = _run_nested(expand_enhanced=False)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "spi.master inner" in out
    assert "spi.slave inner" in out


def test_nested_preserve_renders_invert():
    """保留路径：invert 端口（invert master）渲染。"""
    r = _run_nested(expand_enhanced=False)
    assert r["success"]
    out = r["output"]
    assert "invert master" in out


def test_nested_preserve_token_complete():
    """保留路径：nested/invert 样本 token 完整。"""
    r = _run_nested(expand_enhanced=False)
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

    assert strip_all(out) == strip_all(NESTED_SRC)


def test_nested_expand_consumes():
    """展开路径：嵌套类型被消费（不残留 type.role 引用）。"""
    r = _run_nested()
    assert r["success"]
    out = r["output"]
    assert "spi.master inner" not in out
    assert "type wrap" not in out
