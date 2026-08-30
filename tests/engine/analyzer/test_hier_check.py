"""test_hier_check.py — 层次引用解析器（hier_check 插件）+ width 消费。

覆盖：`a.b` 中 a 是实例时跨模块成员宽度解析（端口/内部成员/覆盖参数/
嵌套链），以及 width_check W201 的跨模块截断检出（此前保守 None 漏检）。
对标 slang 按需解析（references.md「层次引用解析机制调研」）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.checker import ProjectChecker


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


class TestHierWidth:
    """跨模块成员宽度：a.b（a 实例）→ 被实例化模块端口/内部成员宽度。"""

    def _setup(self, tmp_path, sub_src: str) -> None:
        (tmp_path / "sub.sv").write_text(sub_src, encoding="utf-8")

    def _check(self, checker, tmp_path, top_src: str) -> list:
        top = tmp_path / "top.sv"
        top.write_text(top_src, encoding="utf-8")
        report = checker.check(str(top))
        out = []
        for f in report["files"]:
            for d in f["semantic"]:
                if d.get("code") == "W201":
                    out.append(d["message"])
        return out

    def test_port_member_truncation(self, checker, tmp_path):
        """a.b（b 是端口）：sub.p1 8 位连 4 位 LHS → 跨模块截断 W201。"""
        self._setup(
            tmp_path,
            "module sub (input wire [7:0] p1, output wire [3:0] p2);\n"
            "  assign p2 = p1[3:0];\n"
            "endmodule\n",
        )
        msgs = self._check(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [7:0] x;\n"
            "  sub u_sub (x, y);\n"
            "  wire [3:0] narrow;\n  assign narrow = u_sub.p1;\n"  # 8 位端口 → 4 位 LHS 截断
            "  wire y;\n"
            "endmodule\n",
        )
        assert any("8 位" in m and "4 位" in m for m in msgs)

    def test_port_member_equal_clean(self, checker, tmp_path):
        """a.b 等宽 → 不报。"""
        self._setup(
            tmp_path,
            "module sub (input wire [7:0] p1);\nendmodule\n",
        )
        msgs = self._check(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [7:0] x;\n"
            "  sub u_sub (x);\n"
            "  wire [7:0] ok;\n  assign ok = u_sub.p1;\n"
            "endmodule\n",
        )
        assert msgs == []

    def test_internal_member_width(self, checker, tmp_path):
        """a.b（b 是目标模块内部 reg）：inner [5:0] → 6 位。"""
        self._setup(
            tmp_path,
            "module sub (input wire [7:0] p1);\n"
            "  reg [5:0] inner;\n"
            "endmodule\n",
        )
        msgs = self._check(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [7:0] x;\n"
            "  sub u_sub (x);\n"
            "  wire [3:0] narrow;\n  assign narrow = u_sub.inner;\n"  # 6 位内部成员 → 4 位截断
            "endmodule\n",
        )
        assert any("6 位" in m and "4 位" in m for m in msgs)

    def test_override_param_width(self, checker, tmp_path):
        """a.b + 覆盖参数：#(.WIDTH(4)) → 端口 4 位，等宽/扩展均不报。"""
        self._setup(
            tmp_path,
            "module sub #(parameter WIDTH = 8) (input wire [WIDTH-1:0] p1);\n"
            "endmodule\n",
        )
        msgs = self._check(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [3:0] x;\n"
            "  sub #(.WIDTH(4)) u_sub (x);\n"  # 4 位连 4 位端口
            "  wire [7:0] wide;\n  assign wide = u_sub.p1;\n"  # 4 位端口 → 8 位 LHS 扩展不报
            "  wire [3:0] tight;\n  assign tight = u_sub.p1;\n"  # 4 位 == 4 位不报
            "endmodule\n",
        )
        assert msgs == []

    def test_nested_chain(self, checker, tmp_path):
        """a.b.c：a 实例 → b 是中间模块实例 → c 端口宽度。"""
        self._setup(
            tmp_path,
            "module leaf (input wire [11:0] c1);\nendmodule\n"
            "module mid (input wire [7:0] b1);\n"
            "  leaf u_leaf (x);\n"
            "  wire x;\n"
            "endmodule\n",
        )
        msgs = self._check(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [7:0] x;\n"
            "  mid u_mid (x);\n"
            "  wire [3:0] narrow;\n  assign narrow = u_mid.u_leaf.c1;\n"  # 12 位 → 4 位截断
            "endmodule\n",
        )
        assert any("12 位" in m and "4 位" in m for m in msgs)

    def test_indexed_member_conservative(self, checker, tmp_path):
        """a.b[i]（含下标段）→ 保守不推断（HierSuffix 边界）。"""
        self._setup(
            tmp_path,
            "module sub (input wire [7:0] p1);\n"
            "  reg [7:0] mem [0:3];\n"
            "endmodule\n",
        )
        msgs = self._check(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [7:0] x;\n"
            "  sub u_sub (x);\n"
            "  wire [3:0] v;\n  assign v = u_sub.mem[2];\n"  # 含下标 → None 保守
            "endmodule\n",
        )
        assert msgs == []

    def test_local_member_unaffected(self, checker, tmp_path):
        """本地同名成员仍走本地表（实例名 ≠ 时不受影响）。"""
        self._setup(
            tmp_path,
            "module sub (input wire [7:0] p1);\nendmodule\n",
        )
        msgs = self._check(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [7:0] x;\n"
            "  sub u_sub (x);\n"
            "  wire [15:0] local_w;\n"
            "  wire [3:0] narrow;\n  assign narrow = local_w;\n"  # 本地信号 16 → 4 仍报
            "endmodule\n",
        )
        assert any("16 位" in m and "4 位" in m for m in msgs)
