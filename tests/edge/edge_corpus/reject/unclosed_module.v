// edge reject: 模块未闭合（缺 endmodule）
module m(input clk);
    reg a;
    always @(posedge clk) a <= 1;
