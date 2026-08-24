"""ProjectChecker 跨文件语义检查集成测试（tpc check 引擎）。

覆盖：跨文件递归发现、模块联动检查（W101/W102/W103/WC001）、
语法错误跳过语义、环防护/memo。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.checker import ProjectChecker

ADDER = """\
module adder #(parameter WIDTH = 8) (
    input  wire [WIDTH-1:0] a,
    input  wire [WIDTH-1:0] b,
    output wire [WIDTH-1:0] y
);
    assign y = a + b;
endmodule
"""


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
    return tmp_path


def _find(diags, code):
    return [d for d in diags if d.get("code") == code]


class TestCrossFileDiscovery:
    def test_recursive_discovers_module_file(self, checker, proj):
        top = proj / "top.sv"
        top.write_text(
            "module top;\n"
            "  adder u (.a(1'b0), .b(1'b0), .y());\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        assert "adder" in report["modules"]
        # 两个文件都被分析
        paths = {os.path.basename(f["path"]) for f in report["files"]}
        assert paths == {"top.sv", "adder.sv"}

    def test_cycle_guard(self, checker, proj):
        # A 实例化 B、B 实例化 A（定义文件互指）→ 不死循环
        (proj / "a.sv").write_text(
            "module a;\n  b u_b ();\nendmodule\n", encoding="utf-8"
        )
        (proj / "b.sv").write_text(
            "module b;\n  a u_a ();\nendmodule\n", encoding="utf-8"
        )
        report = checker.check(str(proj / "a.sv"))
        assert "a" in report["modules"]
        assert "b" in report["modules"]


class TestInstChecks:
    def test_unknown_port(self, checker, proj):
        top = proj / "top.sv"
        top.write_text(
            "module top;\n"
            "  adder u (.a(1'b0), .b(1'b0), .nope(1'b0));\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        top_file = [f for f in report["files"] if f["path"].endswith("top.sv")][0]
        w102 = _find(top_file["semantic"], "W102")
        assert len(w102) == 1
        assert "nope" in w102[0]["message"]
        # related 链带模块定义处（跨文件）
        assert w102[0]["related"]
        assert w102[0]["related"][0]["file"].endswith("adder.sv")

    def test_unknown_module(self, checker, proj):
        top = proj / "top.sv"
        top.write_text(
            "module top;\n  ghost_module u ();\nendmodule\n", encoding="utf-8"
        )
        report = checker.check(str(top))
        top_file = [f for f in report["files"] if f["path"].endswith("top.sv")][0]
        w101 = _find(top_file["semantic"], "W101")
        assert len(w101) == 1
        assert "ghost_module" in w101[0]["message"]

    def test_unknown_param_override(self, checker, proj):
        top = proj / "top.sv"
        top.write_text(
            "module top;\n"
            "  adder #(.WIDTH(8), .NOPE(1)) u (.a(1'b0), .b(1'b0), .y());\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        top_file = [f for f in report["files"] if f["path"].endswith("top.sv")][0]
        w103 = _find(top_file["semantic"], "W103")
        assert len(w103) == 1
        assert "NOPE" in w103[0]["message"]

    def test_valid_override_no_report(self, checker, proj):
        top = proj / "top.sv"
        top.write_text(
            "module top;\n"
            "  adder #(.WIDTH(16)) u (.a(1'b0), .b(1'b0), .y());\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        top_file = [f for f in report["files"] if f["path"].endswith("top.sv")][0]
        assert not _find(top_file["semantic"], "W103")

    def test_literal_to_parameterized_port(self, checker, proj):
        top = proj / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire a_sig, b_sig;\n"
            "  adder u (.a(a_sig), .b(b_sig), .y(16'hFFFF));\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        top_file = [f for f in report["files"] if f["path"].endswith("top.sv")][0]
        wc = _find(top_file["semantic"], "WC001")
        assert len(wc) == 1
        assert "16'hFFFF" in wc[0]["message"]
        assert "WIDTH" in wc[0]["message"]
        assert wc[0]["related"][0]["file"].endswith("adder.sv")

    def test_literal_to_fixed_port_no_report(self, checker, proj):
        # 纯数字宽度端口（[7:0]）连字面量 → 正常，不报 WC001
        (proj / "fixed.sv").write_text(
            "module fixed (\n"
            "  input [7:0] a,\n"
            "  output [7:0] y\n"
            ");\n  assign y = a;\nendmodule\n",
            encoding="utf-8",
        )
        top = proj / "top.sv"
        top.write_text(
            "module top;\n"
            "  fixed u (.a(8'hFF), .y());\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        top_file = [f for f in report["files"] if f["path"].endswith("top.sv")][0]
        assert not _find(top_file["semantic"], "WC001")


class TestStageGating:
    def test_syntax_error_skips_semantic(self, checker, proj):
        bad = proj / "bad.sv"
        bad.write_text(
            "module bad (\n  input wire a\n);\n  assign y = a +\nendmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(bad))
        f = report["files"][0]
        assert f["syntax"], "应有语法错误"
        assert not f["semantic"], "语法有错 → 语义阶段跳过"
        assert report["exit_code"] == 1

    def test_clean_file_no_issues(self, checker, proj):
        good = proj / "good.sv"
        good.write_text(
            "module good (\n  input wire a,\n  output wire y\n);\n"
            "  assign y = a;\nendmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(good))
        f = report["files"][0]
        assert not f["syntax"]
        assert not f["semantic"]
        assert report["exit_code"] == 0


class TestNoStructureProtocol:
    """语言包未声明 [checker] 结构协议（如 c4）→ check 退化为 lint+analyze：

    不提取模块、不递归、不注入 module_index；通用语法/语义检查照常。
    验证引擎零语言知识（结构知识全部来自配置，缺配置即无结构行为）。
    """

    def test_c4_degrades_to_generic(self, tmp_path):
        from analyzer.checker import ProjectChecker
        from core.define import GrammarRulesRegister

        c4_checker = ProjectChecker(
            rules_dir="grammar/c4",
            register=GrammarRulesRegister(),  # 独立实例，避免污染全局单例
        )
        src = tmp_path / "prog.c4"
        src.write_text(
            "int main() { int a; a = 1; return a; }", encoding="utf-8"
        )
        try:
            report = c4_checker.check(str(src))
        finally:
            # c4 的 load_all 覆盖了全局配置，恢复 verilog 避免污染后续测试
            # （模式同 tests/languages/c4/test_c4_linter.py 的 fixture teardown）
            from core.config_registry import ConfigRegistry

            ConfigRegistry.load_language(
                "grammar/verilog", plugins_dir="grammar/verilog/plugins"
            )
        f = report["files"][0]
        assert f["parse_ok"] or f["syntax"]  # 正常跑完语法阶段
        assert not f["semantic"]             # c4 无语义插件 → 语义阶段无诊断
        assert report["modules"] == {}       # 无模块表（未声明结构协议）
        assert report["exit_code"] in (0, 1)

    def test_no_modules_without_protocol(self, tmp_path):
        from analyzer.checker import ProjectChecker
        from core.define import GrammarRulesRegister

        ck = ProjectChecker(
            rules_dir="grammar/c4",
            register=GrammarRulesRegister(),  # 独立实例，避免污染全局单例
        )
        src = tmp_path / "p.c4"
        src.write_text("int f() { return 0; }", encoding="utf-8")
        try:
            report = ck.check(str(src))
        finally:
            from core.config_registry import ConfigRegistry

            ConfigRegistry.load_language(
                "grammar/verilog", plugins_dir="grammar/verilog/plugins"
            )
        assert report["modules"] == {}
        assert len(report["files"]) == 1
