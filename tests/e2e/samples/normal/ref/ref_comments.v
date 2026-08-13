// 文件头注释
// 多行文件头
module comments_test(
    input clk,  // 行内注释
    input rst_n /* 块注释 */
);
    // 语句前注释
    wire a;
    /* 块注释单独一行 */
    reg b;
    assign a = clk;  // 行尾注释
    assign b = /* 嵌入注释 */ rst_n;
endmodule
