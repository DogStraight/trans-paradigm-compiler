"""test_typed_ports_check.py — typed_ports 增强语法语义检查（TP 族，ADR-0013）。

组件内 postpass（_check.py）三族检查：
    A 表述完整：type/role 引用存在（TP001/TP002）、显式端口归属（TP003）、
      type 良构（role 端口不重复 TP004 / invert 悬空 TP002 / 自反 TP006）
    B/C 连接正确 + 单驱动：后续检查点（待扩）
pos/neg 各验证：坏输入被 TPxxx error 拦下（analyze 报错阻断展开）；好输入
零 TP 诊断。TP 诊断是 error 级 → ProjectChecker report semantic 阶段可观测。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.checker import ProjectChecker  # noqa: E402


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


def _codes(report):
    return {
        d.get("code")
        for f in report["files"]
        for d in f["semantic"]
    }


def _tp_codes(report):
    """仅 TP 族诊断码（过滤 W001 等既有 warning）。"""
    return {
        d.get("code")
        for f in report["files"]
        for d in f["semantic"]
        if str(d.get("code", "")).startswith("TP")
    }


# ── 好输入基线（零 TP）──────────────────────────────


GOOD_SRC = """module top(
    input clk,
    spi.slave spi_io
);
    impl spi.master (.clk(clk)) => spi_io;
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : input clk, input [7:0] mosi, output cs;
}
"""


def test_good_input_no_tp(checker, tmp_path):
    src = tmp_path / "t.sv"
    src.write_text(GOOD_SRC, encoding="utf-8")
    report = checker.check(str(src))
    assert _tp_codes(report) == set()


# ── A：type/role 引用存在 ────────────────────────────


def test_impl_ref_missing_type(checker, tmp_path):
    """impl 引用不存在的 type → TP001。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl nosuch.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "    slave  : input clk;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP001" in _tp_codes(report)


def test_impl_ref_missing_role(checker, tmp_path):
    """impl 引用 type 存在但 role 不存在 → TP002。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl spi.bogus (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "    slave  : input clk;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP002" in _tp_codes(report)


# ── A：显式端口名归属 ────────────────────────────────


def test_impl_typo_port_reported(checker, tmp_path):
    """impl 显式连接 typo 端口（不在 role 定义端口集）→ TP003。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk), .mosi_typo(data)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi, output cs;\n"
        "    slave  : input clk, input mosi, output cs;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP003" in _tp_codes(report)


def test_impl_valid_ports_clean(checker, tmp_path):
    """impl 显式连接端口 ∈ 定义端口集 → 不报 TP003。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk), .mosi(data), .cs(cs_n)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi, output cs;\n"
        "    slave  : input clk, input mosi, output cs;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP003" not in _tp_codes(report)


# ── A：type 定义良构 ─────────────────────────────────


def test_role_duplicate_port_reported(checker, tmp_path):
    """同一 role 内端口名重复 → TP004。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, input clk;\n"
        "    slave  : input clk;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP004" in _tp_codes(report)


def test_invert_missing_role_reported(checker, tmp_path):
    """role 定义 invert 引用不存在的 role → TP002。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "    slave  : invert nosuch;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP002" in _tp_codes(report)


def test_invert_self_reported(checker, tmp_path):
    """invert 自反引用自身 → TP006。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "    slave  : invert slave;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP006" in _tp_codes(report)
