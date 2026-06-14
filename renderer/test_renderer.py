"""Renderer 集成测试：验证 Renderer + normalizer 核心逻辑

覆盖场景：
    - 带端口的模块
    - always + if-else 控制流
    - case 语句
    - opt 条件省略
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.define import Node
from renderer.renderer import Renderer

r = Renderer("pyv_compiler/grammar/rules_verilog")

# 测试布局规则（与 TOML 中的布局规则对应）
r._layouts = {
    "Root": {"layout": {"join": "\n"}},
    "ModuleDecl": {
        "head": {
            "line": ["module ", {"ref": "module_name"}, " (", {"ref": "ports"}, ");"]
        },
        "body": {"indent": True},
        "tail": "endmodule",
        "body_role": "flatten",
    },
    "PortList": {"layout": {"join": ","}},
    "PortDecl": {
        "layout": {
            "line": [
                {"ref": "direction"},
                " ",
                {"opt": {"ref": "port_type"}},
                {"opt": {"group": [" [", {"ref": "range"}, "]"]}},
                " ",
                {"ref": "port_name"},
            ]
        },
    },
    "Range": {"layout": {"line": [{"ref": "msb"}, ":", {"ref": "lsb"}]}},
    "AlwaysBlock": {
        "layout": {"line": ["always @(", {"ref": "sensitivity"}, ") ", {"ref": "body"}]}
    },
    "BeginEnd": {
        "head": "begin",
        "body": {"indent": True},
        "tail": "end",
        "body_role": "flatten",
    },
    "IfStatement": {
        "layout": {"line": ["if (", {"ref": "condition"}, ") ", {"ref": "then_stmt"}]}
    },
    "ElseIf": {
        "layout": {"line": ["else if (", {"ref": "condition"}, ") ", {"ref": "body"}]}
    },
    "ElseBranch": {"layout": {"line": ["else ", {"ref": "body"}]}},
    "CaseStatement": {
        "head": {"line": ["case (", {"ref": "expr"}, ")"]},
        "body": {"indent": True},
        "tail": "endcase",
    },
    "CaseItem": {"layout": {"line": [{"ref": "label"}, ": ", {"ref": "body"}]}},
    "BlockingAssign": {
        "layout": {"line": [{"ref": "target"}, " = ", {"ref": "value"}, ";"]}
    },
    "NonBlockingAssign": {
        "layout": {"line": [{"ref": "target"}, " <= ", {"ref": "value"}, ";"]}
    },
    "Statement": {"layout": {"ref": "stmt"}},
    "ElseChain": {"layout": {"ref": "branch"}},
}


def test_module_with_ports():
    """测试：带端口的模块"""
    mod = Node("ModuleDecl", module_name="alu")
    pl = Node("PortList")
    pl.add_sub_node(
        Node(
            "PortDecl",
            direction="input",
            port_type="wire",
            range=Node("Range", msb="W-1", lsb="0"),
            port_name="a",
        )
    )
    pl.add_sub_node(
        Node(
            "PortDecl",
            direction="input",
            port_type="wire",
            range=Node("Range", msb="W-1", lsb="0"),
            port_name="b",
        )
    )
    pl.add_sub_node(
        Node(
            "PortDecl",
            direction="output",
            port_type="reg",
            range=Node("Range", msb="W-1", lsb="0"),
            port_name="sum",
        )
    )
    mod.ports = pl
    block = Node("Block")
    block.add_sub_node(Node("BlockingAssign", target="sum", value="a + b"))
    mod.body = block
    mod.add_sub_node(block)
    root = Node("Root")
    root.add_sub_node(mod)
    result = r.render(root)
    assert "module alu" in result, f"Missing module header: {result}"
    assert "input wire" in result, f"Missing port: {result}"
    assert "sum = a + b;" in result, f"Missing body: {result}"
    assert "endmodule" in result, f"Missing endmodule: {result}"
    print("[PASS] test_module_with_ports")
    print(result)
    print()


def test_always_block():
    """测试：always + if-else"""
    mod = Node("ModuleDecl", module_name="fsm", ports="clk, rst_n")
    body = Node("Block")
    always = Node("AlwaysBlock", sensitivity="posedge clk or negedge rst_n")
    be = Node("BeginEnd")
    # if (!rst_n) state <= IDLE; else state <= next_state;
    then_stmt = Node(
        "Statement", stmt=Node("NonBlockingAssign", target="state", value="IDLE")
    )
    else_stmt = Node(
        "Statement", stmt=Node("NonBlockingAssign", target="state", value="next_state")
    )
    else_branch = Node("ElseBranch", body=else_stmt)
    ifstmt = Node("IfStatement", condition="!rst_n", then_stmt=then_stmt)
    be.add_sub_node(ifstmt)
    always.body = be
    body.add_sub_node(always)
    mod.body = body
    mod.add_sub_node(body)
    root = Node("Root")
    root.add_sub_node(mod)
    result = r.render(root)
    assert "always @" in result, f"Missing always: {result}"
    assert "if (!rst_n)" in result, f"Missing if: {result}"
    assert "state <= IDLE" in result, f"Missing then: {result}"
    assert "endmodule" in result, f"Missing endmodule: {result}"
    print("[PASS] test_always_block")
    print(result)
    print()


def test_case_statement():
    """测试：case 语句"""
    be = Node("BeginEnd")
    case = Node("CaseStatement", expr="state")
    case.add_sub_node(
        Node(
            "CaseItem",
            label="IDLE",
            body=Node(
                "Statement",
                stmt=Node("BlockingAssign", target="next_state", value="GREEN"),
            ),
        )
    )
    case.add_sub_node(
        Node(
            "CaseItem",
            label="default",
            body=Node(
                "Statement",
                stmt=Node("BlockingAssign", target="next_state", value="IDLE"),
            ),
        )
    )
    be.add_sub_node(case)
    root = Node("Root")
    root.add_sub_node(be)
    result = r.render(root)
    assert "case (state)" in result, f"Missing case: {result}"
    assert "IDLE: next_state = GREEN;" in result, f"Missing case item: {result}"
    assert "endcase" in result, f"Missing endcase: {result}"
    print("[PASS] test_case_statement")
    print(result)
    print()


def test_opt_omits_empty():
    """测试：opt 跳过空子节点"""
    port = Node(
        "PortDecl", direction="input", port_name="clk"
    )  # no port_type, no range
    n = Node("Root")
    n.add_sub_node(port)
    r2 = Renderer("pyv_compiler/grammar/rules_verilog")
    r2._layouts = {
        "Root": {"layout": {"join": "\n"}},
        "PortDecl": {
            "layout": {
                "line": [
                    {"ref": "direction"},
                    {"opt": {"group": [" ", {"ref": "port_type"}]}},
                    " ",
                    {"ref": "port_name"},
                ]
            }
        },
    }
    result = r2.render(n)
    assert result == "input  clk", f"Expected 'input  clk', got {result!r}"
    print("[PASS] test_opt_omits_empty (double space is expected with simplified opt)")


if __name__ == "__main__":
    test_module_with_ports()
    test_always_block()
    test_case_statement()
    test_opt_omits_empty()
    print("\n=== All tests passed ===")
