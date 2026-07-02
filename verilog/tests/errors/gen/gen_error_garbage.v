// Test file for error-tolerant parsing
// Contains garbage lines interspersed with valid Verilog
/* ERROR: module error_test ( */
input wire clk
/* ERROR: , */
/* ERROR: input wire rstn , */
/* ERROR: this is total garbage that should not parse , */
output wire [7:0] data
/* ERROR: ) ; */
// valid register declaration
reg [7:0] counter;
/* ERROR: some random stuff here */
wire flag;
// valid always block
always @(posedge clk or negedge rstn) if (/* ERROR: begin */) /* ERROR: begin */
if (!rstn /* ERROR: counter <= 8'b0 ; */) /* ERROR: counter <= 8'b0 ; */ /* ERROR: counter <= 8'b0 ; */
/* ERROR: else */
counter <= counter + 1'b1;
/* ERROR: end */