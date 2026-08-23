// edge: generate/for + casex/casez + task inout + 超长拼接
module gen_inst #(parameter N = 4) (input clk, input [N-1:0] sel, output [N*8-1:0] d);
    genvar g;

    generate
        for (g = 0; g < N; g = g + 1) begin : gen_byte
            assign d[g*8 +: 8] = sel[g] ? 8'hFF : 8'h00;
        end
    endgenerate

    task automatic swap;
        inout [7:0] x;
        inout [7:0] y;
        reg [7:0] t;
        begin
            t = x;
            x = y;
            y = t;
        end
    endtask

    always @(*) begin
        casex (sel)
            4'b1xxx: d = {8'hAA, 8'hBB, 8'hCC, 8'hDD, 8'hEE, 8'h11, 8'h22, 8'h33};
            4'bx1xx: d = 32'h0;
            default: d = {N{8'h00}};
        endcase
    end
endmodule
