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


# ── elaboration 层 2：端口连接展开（ADR-0008） ──────────────

class TestElaborationConnections:
    """层 2 端口连接展开：NamedPortList / OrderedPortList → PortConnection。

    验证连接结构从 AST 展开（端口名 → 连接信号名），经 context.extra
    注入插件可消费；位置连接按序收集。
    """

    def test_named_connections_expanded(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] x, y, z;\n"
            "  adder u1 (.a(x), .b(y), .y(z));\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        # 连接展开挂在 FileResult.connections（checker._memo 内部状态）
        conns = _collect_connections(checker)
        assert len(conns) == 1
        c = conns[0]
        assert c["inst_name"] == "u1"
        assert c["module_name"] == "adder"
        assert c["connects"] == {"a": "x", "b": "y", "y": "z"}

    def test_ordered_connections_expanded(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] x, y, z;\n"
            "  adder u2 (x, y, z);\n"
            "endmodule\n",
            encoding="utf-8",
        )
        checker.check(str(top))
        conns = _collect_connections(checker)
        assert len(conns) == 1
        assert conns[0]["ordered"] == ["x", "y", "z"]
        assert conns[0]["connects"] == {}

    def test_mixed_named_and_unconnected(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] x, z;\n"
            "  adder u3 (.a(x), .y(z));\n"  # b 未连接（.b() 缺省）
            "endmodule\n",
            encoding="utf-8",
        )
        checker.check(str(top))
        conns = _collect_connections(checker)
        assert conns[0]["connects"] == {"a": "x", "y": "z"}

    def test_connections_injected_for_each_file(self, checker, tmp_path):
        """顶层文件与模块定义文件各自有连接注入（模块文件内实例化也展开）。"""
        (tmp_path / "child.sv").write_text(
            "module child;\n  wire c;\nendmodule\n", encoding="utf-8"
        )
        (tmp_path / "mid.sv").write_text(
            "module mid;\n  child m1 ();\nendmodule\n", encoding="utf-8"
        )
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n  mid t1 ();\nendmodule\n", encoding="utf-8"
        )
        checker.check(str(top))
        conns = _collect_connections(checker)
        by_inst = {c["inst_name"]: c for c in conns}
        # top 文件实例化 mid；mid 文件实例化 child——两处都展开
        assert by_inst["t1"]["module_name"] == "mid"
        assert by_inst["m1"]["module_name"] == "child"


def _collect_connections(checker):
    """从 checker._memo（FileResult.connections）收集连接展开（测试内联访问）。"""
    out = []
    for fr in checker._memo.values():
        for c in fr.connections:
            out.append(
                {
                    "inst_name": c.inst_name,
                    "module_name": c.module_name,
                    "connects": dict(c.connects),
                    "ordered": list(c.ordered),
                }
            )
    return out


# ── elaboration 层 3：驱动/负载图（ADR-0008） ──────────────


class TestElaborationSignalGraph:
    """层 3 全工程信号驱动/负载图：output 连接=驱动，input 连接=负载。

    验证 signal_graph 按端口方向正确分类驱动源/负载，供 UNUSED/
    UNDRIVEN/MULTIDRIVEN 规则消费。
    """

    def test_output_drives_input_loads(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] x, y, z;\n"
            "  adder u1 (.a(x), .b(y), .y(z));\n"
            "endmodule\n",
            encoding="utf-8",
        )
        checker.check(str(top))
        graph = checker._signal_graph
        # x/y 连 input a/b → 负载（u1 读取）；z 连 output y → 驱动（u1 驱动）
        # 键 = (模块名, 信号名)——跨模块同名信号隔离（2026-08-29 修复）
        # inst_ref 格式 = "文件名:实例名"
        assert "u1" in [r.split(":")[-1] for r in graph[("top", "x")]["loads"]]
        assert "u1" in [r.split(":")[-1] for r in graph[("top", "y")]["loads"]]
        assert "u1" in [r.split(":")[-1] for r in graph[("top", "z")]["drivers"]]
        assert "u1" not in [r.split(":")[-1] for r in graph[("top", "z")]["loads"]]

    def test_inout_both(self, checker, tmp_path):
        (tmp_path / "mem.sv").write_text(
            "module mem (inout wire [7:0] d);\nendmodule\n", encoding="utf-8"
        )
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n  wire [7:0] bus;\n  mem m1 (.d(bus));\nendmodule\n",
            encoding="utf-8",
        )
        checker.check(str(top))
        graph = checker._signal_graph
        insts_d = [r.split(":")[-1] for r in graph[("top", "bus")]["drivers"]]
        insts_l = [r.split(":")[-1] for r in graph[("top", "bus")]["loads"]]
        assert "m1" in insts_d
        assert "m1" in insts_l

    def test_constant_not_in_graph(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] z;\n"
            "  adder u1 (.a(1'b0), .b(8'hFF), .y(z));\n"  # 常量不建图
            "endmodule\n",
            encoding="utf-8",
        )
        checker.check(str(top))
        graph = checker._signal_graph
        assert ("top", "1'b0") not in graph
        assert ("top", "8'hFF") not in graph
        assert "u1" in [r.split(":")[-1] for r in graph[("top", "z")]["drivers"]]

    def test_multi_driver_detected(self, checker, tmp_path):
        """同一信号被两个实例 output 连接 → 多驱动（MULTIDRIVEN 地基）。"""
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] a, b, s;\n"
            "  adder u1 (.a(a), .b(b), .y(s));\n"
            "  adder u2 (.a(a), .b(b), .y(s));\n"  # s 被双驱动
            "endmodule\n",
            encoding="utf-8",
        )
        checker.check(str(top))
        graph = checker._signal_graph
        assert len(graph[("top", "s")]["drivers"]) == 2

    def test_signal_graph_injected_in_context(self, checker, tmp_path):
        """信号图经 context.extra 注入（postpass 可消费）。"""
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n  wire [7:0] x, y, z;\n"
            "  adder u1 (.a(x), .b(y), .y(z));\nendmodule\n",
            encoding="utf-8",
        )
        checker.check(str(top))
        # 注入发生在 analyze 的 _external_extra（analyze() 重建 context 合并）
        for fr in checker._memo.values():
            if fr.analyzer is not None:
                assert "signal_graph" in fr.analyzer._external_extra
                assert "connections" in fr.analyzer._external_extra


# ── 跨文件端口完整性：未连接端口 W104（elaboration 层 2 之上） ──


class TestMissingPortCheck:
    """未连接端口检查（对标 Veryl missing_port / Verilator PINMISSING）。

    模块 input/output 端口在实例化时未连接 → W104；已连接/未用的 inout
    不报。依赖 elaboration 层 2 连接展开 + 模块端口方向。
    """

    def test_missing_input_reported(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] x;\n"
            "  adder u1 (.a(x), .y());\n"  # b 未连接
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        w104 = _find(
            [d for f in report["files"] for d in f["semantic"]], "W104"
        )
        assert any("b" in d["message"] for d in w104)

    def test_all_connected_no_w104(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] x, y, z;\n"
            "  adder u1 (.a(x), .b(y), .y(z));\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        codes = {d.get("code") for f in report["files"] for d in f["semantic"]}
        assert "W104" not in codes

    def test_output_unconnected_reported(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] x, y;\n"
            "  adder u1 (.a(x), .b(y));\n"  # output y 未连接
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        w104 = _find(
            [d for f in report["files"] for d in f["semantic"]], "W104"
        )
        assert any("y" in d["message"] for d in w104)

    def test_inout_unconnected_exempt(self, checker, tmp_path):
        (tmp_path / "mem.sv").write_text(
            "module mem (input wire a, inout wire d);\nendmodule\n",
            encoding="utf-8",
        )
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n  wire x;\n  mem m1 (.a(x));\nendmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        w104 = _find(
            [d for f in report["files"] for d in f["semantic"]], "W104"
        )
        # inout d 未连接不报；input a 已连接
        assert not any("d" in d["message"] for d in w104)


# ── 多驱动检查 W105（elaboration 层 3 信号图之上） ──────────


class TestMultiDriverCheck:
    """多驱动检查（对标 Verilator MULTIDRIVEN / Spyglass W415）。

    同一信号被多个实例 output 连接 → W105（error 级）。基于层 3
    signal_graph 的 drivers 集合。
    """

    def test_multi_driver_reported(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] a, b, s;\n"
            "  adder u1 (.a(a), .b(b), .y(s));\n"
            "  adder u2 (.a(a), .b(b), .y(s));\n"  # s 被双驱动
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        w105 = _find(
            [d for f in report["files"] for d in f["semantic"]], "W105"
        )
        assert len(w105) == 1
        assert "s" in w105[0]["message"]

    def test_single_driver_no_w105(self, checker, tmp_path):
        (tmp_path / "adder.sv").write_text(ADDER, encoding="utf-8")
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire [7:0] a, b, s;\n"
            "  adder u1 (.a(a), .b(b), .y(s));\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        codes = {d.get("code") for f in report["files"] for d in f["semantic"]}
        assert "W105" not in codes

    def test_cross_file_multi_driver_reported_once(self, checker, tmp_path):
        """跨文件多驱动：信号在两个文件分别被驱动 → 报一次（所在文件）。"""
        (tmp_path / "drv.sv").write_text(
            "module drv (output wire q);\nendmodule\n", encoding="utf-8"
        )
        top = tmp_path / "top.sv"
        top.write_text(
            "module top;\n"
            "  wire s;\n"
            "  drv d1 (.q(s));\n"
            "  drv d2 (.q(s));\n"  # 同文件双驱动
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(top))
        w105 = _find(
            [d for f in report["files"] for d in f["semantic"]], "W105"
        )
        assert len(w105) == 1


# ── inout 端口须 tri W106（svlint inout_with_tri = Veryl missing_tri） ──


class TestInoutTriCheck:
    """inout 端口数据类型须为 tri（三态总线语义）。"""

    def test_inout_wire_reported(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t (inout wire [7:0] d);\n"  # wire 不是 tri
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        w106 = _find(
            [d for f in report["files"] for d in f["semantic"]], "W106"
        )
        assert len(w106) == 1
        assert "wire" in w106[0]["message"]

    def test_inout_tri_clean(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t (inout tri [7:0] d);\n"  # tri 正确
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        codes = {d.get("code") for f in report["files"] for d in f["semantic"]}
        assert "W106" not in codes

    def test_input_output_not_affected(self, checker, tmp_path):
        """input/output 端口不检查 tri（仅 inout）。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t (input wire a, output wire y);\n"
            "  assign y = a;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        codes = {d.get("code") for f in report["files"] for d in f["semantic"]}
        assert "W106" not in codes
