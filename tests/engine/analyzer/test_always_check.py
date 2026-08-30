"""test_always_check.py — always 写法风格检查（always_check 插件）。

覆盖：AW001 时序块阻塞赋值（启用后检出、组合不报、默认关不刷屏）；
AW002 同块同信号混用 =/<=（启用后检出、单运算符不报、默认关）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.checker import ProjectChecker


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


def _codes(report):
    return {
        d.get("code")
        for f in report["files"]
        for d in f["semantic"]
    }


class TestAlwaysCheck:
    def _check(self, checker, src_text: str, tmp_path) -> set:
        src = tmp_path / "t.sv"
        src.write_text(src_text, encoding="utf-8")
        return _codes(checker.check(str(src)))

    def test_default_off(self, checker, tmp_path):
        """默认配置：AW001/AW002 不启用（default=false，0.1.1 不刷屏）。"""
        codes = self._check(
            checker,
            "module t;\n"
            "  reg clk, d, q;\n"
            "  always @(posedge clk) q = d;\n"  # 时序块阻塞赋值
            "endmodule\n",
            tmp_path,
        )
        assert "AW001" not in codes
        assert "AW002" not in codes

    def test_aw001_blocking_in_timing(self, checker, tmp_path):
        """启用后：时序 always 内阻塞赋值 → AW001。"""
        checker._enabled_rules = ["AW001"]
        try:
            codes = self._check(
                checker,
                "module t;\n"
                "  reg clk, rst_n, d, q;\n"
                "  always @(posedge clk or negedge rst_n) begin\n"
                "    if (!rst_n)\n"
                "      q = 1'b0;\n"  # 阻塞赋值 → AW001
                "    else\n"
                "      q = d;\n"
                "  end\n"
                "endmodule\n",
                tmp_path,
            )
            assert "AW001" in codes
        finally:
            checker._enabled_rules = None

    def test_aw001_nonblocking_clean(self, checker, tmp_path):
        """启用后：时序 always 全用 <= → 不报。"""
        checker._enabled_rules = ["AW001"]
        try:
            codes = self._check(
                checker,
                "module t;\n"
                "  reg clk, rst_n, d, q;\n"
                "  always @(posedge clk or negedge rst_n) begin\n"
                "    if (!rst_n)\n"
                "      q <= 1'b0;\n"
                "    else\n"
                "      q <= d;\n"
                "  end\n"
                "endmodule\n",
                tmp_path,
            )
            assert "AW001" not in codes
        finally:
            checker._enabled_rules = None

    def test_aw001_comb_clean(self, checker, tmp_path):
        """启用后：组合 always 内阻塞赋值是惯例 → 不报。"""
        checker._enabled_rules = ["AW001"]
        try:
            codes = self._check(
                checker,
                "module t;\n"
                "  reg a, b, y;\n"
                "  always @(*) y = a & b;\n"
                "endmodule\n",
                tmp_path,
            )
            assert "AW001" not in codes
        finally:
            checker._enabled_rules = None

    def test_aw002_mixed_same_signal(self, checker, tmp_path):
        """启用后：同一 always 内同一信号混用 = 与 <= → AW002。"""
        checker._enabled_rules = ["AW002"]
        try:
            codes = self._check(
                checker,
                "module t;\n"
                "  reg clk, d, q;\n"
                "  always @(posedge clk) begin\n"
                "    q = d;\n"  # 阻塞
                "    q <= d;\n"  # 非阻塞 → 混用
                "  end\n"
                "endmodule\n",
                tmp_path,
            )
            assert "AW002" in codes
        finally:
            checker._enabled_rules = None

    def test_aw002_single_op_clean(self, checker, tmp_path):
        """启用后：同一信号只用一种运算符 → 不报。"""
        checker._enabled_rules = ["AW002"]
        try:
            codes = self._check(
                checker,
                "module t;\n"
                "  reg clk, d, q;\n"
                "  always @(posedge clk) begin\n"
                "    q <= d;\n"
                "    q <= d;\n"  # 全非阻塞
                "  end\n"
                "endmodule\n",
                tmp_path,
            )
            assert "AW002" not in codes
        finally:
            checker._enabled_rules = None

    def test_aw002_distinct_signals_clean(self, checker, tmp_path):
        """启用后：不同信号各自用不同运算符 → 不报。"""
        checker._enabled_rules = ["AW002"]
        try:
            codes = self._check(
                checker,
                "module t;\n"
                "  reg clk, d, q1, q2;\n"
                "  always @(posedge clk) begin\n"
                "    q1 = d;\n"
                "    q2 <= d;\n"
                "  end\n"
                "endmodule\n",
                tmp_path,
            )
            assert "AW002" not in codes
        finally:
            checker._enabled_rules = None
