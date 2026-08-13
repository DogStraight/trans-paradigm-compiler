module a(
    input clk,
    input rst_n,

    input [7:0] a,
    output [7:0] b,
    output reg b_e = 1'b0
);
    always @(posedge clk)
        b<= a+1'b1;
    
    function [7:0] add;
        
    endfunction

    generate
        
    endgenerate

endmodule