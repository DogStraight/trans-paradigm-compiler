// Test file for error-tolerant parsing
// Contains garbage lines interspersed with valid Verilog
input wire clk
output wire [7:0] data
// valid register declaration
reg [7:0] counter;
wire flag;
// valid always block
always @(posedge clk or negedge rstn) begin
    if (!rstn)
        counter <= 8'b0;
    else
        counter <= counter + 1'b1;
end

assign flag = counter[0];
// more garbage