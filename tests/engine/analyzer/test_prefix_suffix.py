"""test_prefix_suffix.py — 命名前后缀语义约定（NC014-016，默认关）。

覆盖：NC014 端口方向后缀不一致（input data_o 防接反）、NC015/016 类型
后缀不一致（wire x_r / reg q_w 防类型混淆）、`_` 前缀豁免、默认关零
刷屏、require 模式经规则数据开启后生效。蓝本 svlint prefix_input/
output/inout（decisions/0004「落地演进」）。
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


class TestPrefixSuffix:
    def _check(self, checker, src_text: str, tmp_path) -> set:
        src = tmp_path / "t.sv"
        src.write_text(src_text, encoding="utf-8")
        return _codes(checker.check(str(src)))

    def test_default_off(self, checker, tmp_path):
        """默认配置：NC014-016 不启用（default=false，不刷屏）。"""
        codes = self._check(
            checker,
            "module t (input wire data_o, output wire [7:0] addr);\n"
            "  wire [7:0] x_r;\n"
            "  reg q_w;\n"
            "endmodule\n",
            tmp_path,
        )
        assert not (codes & {"NC014", "NC015", "NC016"})

    def test_direction_mismatch_reported(self, checker, tmp_path):
        """input 端口以 _o 结尾（方向接反）→ NC014。"""
        checker._enabled_rules = ["NC014"]
        try:
            codes = self._check(
                checker,
                "module t (input wire data_o, output wire [7:0] addr_o);\n"
                "endmodule\n",
                tmp_path,
            )
            assert "NC014" in codes  # data_o: input 带 output 后缀
        finally:
            checker._enabled_rules = None

    def test_direction_match_clean(self, checker, tmp_path):
        """后缀与声明方向一致 / 无后缀 → 不报。"""
        checker._enabled_rules = ["NC014"]
        try:
            codes = self._check(
                checker,
                "module t (\n"
                "  input wire data_i,\n"
                "  output wire [7:0] addr_o,\n"
                "  inout wire bus_io,\n"
                "  input wire clk,\n"  # 无后缀不报（默认非 require）
                "  input wire rst_n\n"  # _n 非方向后缀不报
                ");\n"
                "endmodule\n",
                tmp_path,
            )
            assert "NC014" not in codes
        finally:
            checker._enabled_rules = None

    def test_kind_suffix_mismatch_reported(self, checker, tmp_path):
        """wire 以 _r 结尾 / reg 以 _w 结尾（类型混淆）→ NC015/NC016。"""
        checker._enabled_rules = ["NC015", "NC016"]
        try:
            codes = self._check(
                checker,
                "module t;\n"
                "  wire [7:0] x_r;\n"  # wire 带 reg 后缀 → NC015
                "  reg q_w;\n"  # reg 带 wire 后缀 → NC016
                "endmodule\n",
                tmp_path,
            )
            assert "NC015" in codes
            assert "NC016" in codes
        finally:
            checker._enabled_rules = None

    def test_kind_suffix_match_clean(self, checker, tmp_path):
        """wire → _w / reg → _r / 无后缀 → 不报。"""
        checker._enabled_rules = ["NC015", "NC016"]
        try:
            codes = self._check(
                checker,
                "module t;\n"
                "  wire [7:0] addr_w;\n"
                "  reg q_r;\n"
                "  wire plain;\n"  # 无后缀不报（默认非 require）
                "endmodule\n",
                tmp_path,
            )
            assert not (codes & {"NC015", "NC016"})
        finally:
            checker._enabled_rules = None

    def test_underscore_prefix_exempt(self, checker, tmp_path):
        """`_` 前缀（占位/故意不用约定）→ 豁免。"""
        checker._enabled_rules = ["NC014", "NC015", "NC016"]
        try:
            codes = self._check(
                checker,
                "module t (input wire _data_o);\n"
                "  wire _x_r;\n"
                "  reg _q_w;\n"
                "endmodule\n",
                tmp_path,
            )
            assert not (codes & {"NC014", "NC015", "NC016"})
        finally:
            checker._enabled_rules = None

    def test_require_mode_via_rule_data(self, checker, tmp_path):
        """require = true 时无后缀也报（规则数据开启强约定）。"""
        from core import check_registry

        rules = check_registry.get_check_rules()
        base = next(r for r in rules if r["id"] == "NC014")
        patched = dict(base)
        patched["require"] = True
        # 直接测 handler（require 分支）——避免改全局规则表
        from grammar.verilog.plugins.checks.name_check.rules import (
            _prefix_suffix_check as psc,
        )

        class FakeSym:
            name = "data"
            kind = "port"

            class _N:
                direction = "input"

            decl_node = _N()

        msg = psc.check_direction_suffix(FakeSym(), patched, None)
        assert msg is not None and "期望 _i" in msg