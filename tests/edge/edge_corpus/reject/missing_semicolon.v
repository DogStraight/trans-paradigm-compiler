// edge reject: 缺分号（linter 应拦）
module m(input clk);
    reg a
    always @(posedge clk) a <= 1;
endmodule
