// Test: 多维数组声明
module array2d_test ( ) ;
reg [7:0] mem2d[0:3][0:7];
reg [31:0] matrix[0:7][0:31];
reg [3:0] single_arr[0:15];
integer i, j;
always @(posedge clk) begin
    if ( we ) begin
    mem2d[addr_h][addr_l] <= data_in;
end

end