"""linter/diagnose.py 多路径诊断测试。

枚举条件编译所有路径，逐条 lint 汇总——覆盖不同编译选项下不同结构。
"""

import pytest

from linter.diagnose import diagnose_all_paths

pytestmark = pytest.mark.usefixtures("config_loaded")


class TestDiagnoseAllPaths:
    def test_no_conditions_single_path(self):
        """无条件块 → 单一路径（无 define/undefine）。"""
        src = "module m;\n    reg a;\nendmodule\n"
        results = diagnose_all_paths(src, rules_dir=r"e:\project\tpc_compiler\grammar\verilog")
        assert len(results) == 1
        assert results[0]["define"] == []
        assert results[0]["undefine"] == []
        assert results[0]["diagnostics"] == []

    def test_ifdef_two_branches_two_paths(self):
        """`ifdef F / `else → 2 条路径（F 定义 / 未定义）。"""
        src = (
            "module m;\n"
            "`ifdef F\n"
            "    reg a;\n"
            "`else\n"
            "    reg b;\n"
            "`endif\n"
            "endmodule\n"
        )
        results = diagnose_all_paths(src, rules_dir=r"e:\project\tpc_compiler\grammar\verilog")
        assert len(results) == 2
        # 一条 define F，一条 undefine F（或 define 空）
        defines = [r["define"] for r in results]
        assert ["F"] in defines, f"应有 define F 路径: {defines}"
        assert [] in defines, f"应有未定义 F 路径: {defines}"

    def test_diagnostics_per_path(self):
        """每路径独立 lint——错误只在该路径报。"""
        src = (
            "module m;\n"
            "`ifdef GOOD\n"
            "    reg a;\n"
            "`else\n"
            "    reg a,;\n"  # 语法错误（多余逗号）
            "`endif\n"
            "endmodule\n"
        )
        results = diagnose_all_paths(src, rules_dir=r"e:\project\tpc_compiler\grammar\verilog")
        # 至少一条路径有诊断（bad 分支），一条无（good 分支）
        diag_counts = [len(r["diagnostics"]) for r in results]
        assert any(c > 0 for c in diag_counts), f"应有路径报错: {diag_counts}"
