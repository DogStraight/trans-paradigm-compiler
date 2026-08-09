// 循环 + 模块项 generate 语法测试（可综合 RTL 子集）
module loops_gen #(
    parameter W = 8
) (
    input  wire [W-1:0] a,
    output wire [W-1:0] y
);
    integer i;
    genvar g;

    // generate for
    generate
        for (g = 0; g < W; g = g + 1) begin : gen_bit
            assign y[g] = a[g];
        end
    endgenerate

    // 模块项级 if generate
    if (W > 4) begin : wide
        wire extra;
        assign extra = a[0];
    end else begin : narrow
        wire extra2;
        assign extra2 = a[0];
    end

    // 模块项级 case generate
    case (W)
        8: begin : w8
            assign y = a;
        end
        default: begin : wd
            assign y = a[0];
        end
    endcase

    always @(*) begin
        i = 0;
        while (i < 4) begin
            i = i + 1;
        end
        repeat (2) i = i + 1;
    end
endmodule
