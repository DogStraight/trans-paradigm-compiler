`define W 8
`define D 256
`define H (`D / 2)
`define RST 0

module buffer #(
    parameter P_W = `W,
    parameter P_D = `D
) (
    input clk,
    input rstn,
    input [`W-1:0] din,
    output reg [`W-1:0] dout
);
    reg [`W-1:0] mem [`D-1:0];
    reg [`W-1:0] head, tail;

    always @(posedge clk) begin
        if (!rstn) begin
            head <= `W'd`RST;
            tail <= `W'd`RST;
            dout <= `W'd`RST;
        end else begin
            mem[tail] <= din;
            tail <= tail + `W'd1;
            if (tail == `H) tail <= `W'd`RST;
            dout <= mem[head];
            head <= head + `W'd1;
            if (head == `H) head <= `W'd`RST;
        end
    end
endmodule
