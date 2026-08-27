// net 类型全谱 + strength/vectored/delay3 + real/time/realtime（nettypes 插件）
module net_types_demo(
    input clk,
    input [7:0] data_in,
    output [7:0] data_out
);

    // 12 种 net_type 全谱
    wire        w_plain;
    tri         t_bus;
    triand      [7:0] t_and;
    trior       t_or;
    tri0        t_0;
    tri1        t_1;
    trireg      (small) t_reg;
    uwire       uw;
    wand        w_and;
    wor         w_or;
    supply0     gnd;
    supply1     vcc;

    // strength + vectored/scalared
    tri (strong0, pull1) driven;
    wand (weak0, highz1) [7:0] wd = 8'h00;
    tri vectored [15:0] vec;
    wand scalared signed [31:0] sc;

    // delay3
    wire #5 wd5;
    tri #(1, 2, 3) wmm;
    wire #(1:2:3) wmt;

    // 变量声明
    real r1, r2 = 1.5;
    realtime rt;
    time t;

    // 常规逻辑
    assign data_out = w_plain ? data_in : 8'h00;

endmodule
