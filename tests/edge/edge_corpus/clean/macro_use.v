// edge: 宏使用 + ifdef + 函数（ANSI 与旧式）
`define WIDTH 16
`define MAX_VAL (`WIDTH'hFFFF)

module macro_use(input clk, input [`WIDTH-1:0] in, output [`WIDTH-1:0] out);
    function automatic [`WIDTH-1:0] sat_add;
        input [`WIDTH-1:0] a;
        input [`WIDTH-1:0] b;
        begin
            sat_add = (a + b > `MAX_VAL) ? `MAX_VAL : a + b;
        end
    endfunction

`ifdef EXTRA
    assign out = sat_add(in, in);
`else
    assign out = sat_add(in, 16'h0001);
`endif
endmodule
