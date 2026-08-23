// edge: 非 ANSI 端口 + 参数化位宽 + 属性（属性挂声明，AttrDecl 注入 ModuleItem）
module counter(clk, rst, out);
    parameter W = 8;
    localparam MAX = (1 << W) - 1;
    input clk;
    input rst;
    output [W-1:0] out;

    (* keep = "true" *) reg [W-1:0] out;

    always @(posedge clk or posedge rst) begin
        if (rst)
            out <= {W{1'b0}};
        else if (out == MAX)
            out <= 8'h00;
        else
            out <= out + 1'b1;
    end
endmodule
