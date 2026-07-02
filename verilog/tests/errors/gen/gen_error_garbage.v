// Test file for error-tolerant parsing
// Contains garbage lines interspersed with valid Verilog
module error_test (
input wire clk
,
input wire rstn ,
this is total garbage that should not parse ,
output wire [7:0] data
) ;
// valid register declaration
reg [7:0] counter;
some random stuff here
wire flag;
// valid always block
always @ ( posedge clk or negedge rstn ) begin
if ( ! rstn )
counter <= 8'b0;
else
counter <= counter + 1'b1;
end