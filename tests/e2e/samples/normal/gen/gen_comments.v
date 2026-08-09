// 文件头注释
// 多行文件头
module comments_test( input clk, input rst_n);

    // 语句前注释
    wire a;
    /* 块注释单独一行 */
    reg b;
    assign a = clk;
    assign b = rst_n;
endmodule
