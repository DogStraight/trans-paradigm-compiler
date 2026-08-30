"""injectors.py — 变异注入器表（检查能力检验：错误类型 → 对应检查检出）。

从**正确基座**（base，对目标检查必须干净）注入**特定错误**（mutate 变换），
验证对应检查必然检出、注入不引发其他检查误报。每个注入器一条：

    target       — 应检出的检查码（recall 断言）
    base         — 正确基座源码（跑注入前先断言无任何诊断）
    mutate       — 错误注入变换（str → str，只改一处）
    enable       — 默认关的规则（目标检查本身，如 NC/AW）
    allowed_extra— 合法连带检出（如删 case default 同时是 CC001+LC001）

基座设计约束：目标检查干净 + 不触发其他检查级联（端口方向/未使用豁免
按 UN001 只查 wire/reg/integer 设计）。错误注入 = 单个语义错误的程序化
生成（变异测试；与 34 个手写精度样本互补，样本量可扩展）。
"""

# 每个注入器：target 默认启用集之外需显式启用的规则
# （default=false 的 NC/AW 族——启用后基座必须按约定命名）

INJECTORS = [
    # ── W201 赋值/端口连接截断 ──────────────────────────────────────
    dict(
        id="W201_assign_trunc",
        target="W201",
        base=(
            "module t;\n"
            "  wire [7:0] a;\n"
            "  wire [3:0] b;\n"
            "  assign a = b;\n"  # 8←4 扩展，无截断
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("assign a = b;", "assign b = a;"),
    ),
    dict(
        id="W201_port_conn_trunc",
        target="W201",
        base=(
            "module sub (input wire [7:0] a_i);\nendmodule\n"
            "module top;\n"
            "  wire [7:0] x;\n"
            "  sub u1 (.a_i(x));\n"  # 8==8 等宽
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("wire [7:0] x;", "wire [15:0] x;"),
    ),
    # ── W202 位选越界 ───────────────────────────────────────────────
    dict(
        id="W202_select_oob",
        target="W202",
        base=(
            "module t;\n"
            "  wire [7:0] v;\n"
            "  wire y;\n"
            "  assign y = v[3];\n"  # 3 ∈ [0,7]
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("v[3]", "v[8]"),
    ),
    # ── LC001 锁存（if 删 else / case 删臂） ─────────────────────────
    dict(
        id="LC001_if_no_else",
        target="LC001",
        base=(
            "module t (input c, d, e);\n"
            "  reg y;\n"
            "  always @* begin\n"
            "    if (c) y = d;\n"
            "    else y = e;\n"
            "  end\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("\n    else y = e;", ""),
    ),
    dict(
        id="LC001_case_drop_arm",
        target="LC001",
        base=(
            "module t (input [1:0] sel);\n"
            "  reg [3:0] y;\n"
            "  always @* begin\n"
            "    case (sel)\n"
            "      2'b00: y = 4'd0;\n"
            "      2'b01: y = 4'd1;\n"
            "      default: y = 4'd2;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n"
        ),
        # default 臂不再赋值 → default 路径 y 保持 → 锁存（default 存在，
        # CC001 仍干净）
        mutate=lambda s: s.replace("default: y = 4'd2;", "default: ;"),
    ),
    # ── CC001 case 无 default ───────────────────────────────────────
    dict(
        id="CC001_drop_default",
        target="CC001",
        base=(
            "module t (input [1:0] sel);\n"
            "  reg [3:0] y;\n"
            "  always @* begin\n"
            "    case (sel)\n"
            "      2'b00: y = 4'd0;\n"
            "      2'b01: y = 4'd1;\n"
            "      default: y = 4'd2;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("      default: y = 4'd2;\n", ""),
        allowed_extra={"LC001"},  # 无 default 且未全覆盖 → 锁存风险
    ),
    # ── W104 未连接端口（命名删连 / 位置缺连） ──────────────────────
    dict(
        id="W104_named_missing",
        target="W104",
        base=(
            "module adder (input wire [7:0] a, input wire [7:0] b,"
            " output wire [7:0] y);\n"
            "  assign y = a + b;\n"
            "endmodule\n"
            "module top (output wire [7:0] z);\n"
            "  wire [7:0] x, y;\n"
            "  adder u1 (.a(x), .b(y), .y(z));\n"
            "  assign x = 8'd0;\n"
            "  assign y = 8'd0;\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace(".b(y), ", ""),
    ),
    dict(
        id="W104_ordered_missing",
        target="W104",
        base=(
            "module adder (input wire [7:0] a, input wire [7:0] b,"
            " output wire [7:0] y);\n"
            "  assign y = a + b;\n"
            "endmodule\n"
            "module top (output wire [7:0] z);\n"
            "  wire [7:0] x, y;\n"
            "  adder u1 (x, y, z);\n"
            "  assign x = 8'd0;\n"
            "  assign y = 8'd0;\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("adder u1 (x, y, z);", "adder u1 (x, z);"),
    ),
    # ── W105 多驱动（assign 双驱动 / 双实例 output） ────────────────
    dict(
        id="W105_dup_assign",
        target="W105",
        base=(
            "module top (output wire [7:0] a);\n"
            "  assign a = 8'd0;\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace(
            "endmodule\n", "  assign a = 8'd1;\nendmodule\n"
        ),
    ),
    dict(
        id="W105_two_inst_output",
        target="W105",
        base=(
            "module sub (output wire [7:0] o);\n"
            "  assign o = 8'd0;\n"
            "endmodule\n"
            "module top (output wire [7:0] z);\n"
            "  sub u1 (.o(z));\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("sub u1 (.o(z));", "sub u1 (.o(z));\n  sub u2 (.o(z));"),
    ),
    # ── UN001 未使用声明 ────────────────────────────────────────────
    dict(
        id="UN001_unused_wire",
        target="UN001",
        base=(
            "module top (output wire [7:0] q);\n"
            "  wire [7:0] a;\n"
            "  assign a = 8'd0;\n"
            "  assign q = a;\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace(
            "  wire [7:0] a;\n",
            "  wire [7:0] a;\n  wire [7:0] unused_x;\n",
        ),
    ),
    # ── NC014 端口方向后缀（默认关，注入器启用） ────────────────────
    dict(
        id="NC014_direction_suffix_mismatch",
        target="NC014",
        enable=["NC014"],
        base=(
            "module top (input wire a_i, output wire b_o);\n"
            "  assign b_o = a_i;\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("a_i", "a_o"),  # input 带 _o 后缀
    ),
    # ── AW001 时序块阻塞赋值（默认关，注入器启用） ──────────────────
    dict(
        id="AW001_blocking_in_timing",
        target="AW001",
        enable=["AW001"],
        base=(
            "module t (input clk, input d, output reg q);\n"
            "  always @(posedge clk) q <= d;\n"
            "endmodule\n"
        ),
        mutate=lambda s: s.replace("q <= d", "q = d"),
    ),
]
