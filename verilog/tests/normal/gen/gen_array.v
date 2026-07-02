// Test: 数组声明 + 数组元素访问 + 域选
module array_test();

    reg [7:0] mem[0:15];
    reg [31:0] data_bus[0:7];
    integer i;
    always @(posedge clk) if (/* ERROR: begin */) /* ERROR: begin */
    if (we /* ERROR: mem [ addr ] <= data_in ; */) /* ERROR: mem [ addr ] <= data_in ; */ /* ERROR: mem [ addr ] <= data_in ; */
    data_out <= mem[addr];
    /* ERROR: end */
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    for (i = 0; i < 8; i = i + 1) 
        if (/* ERROR: data_bus [ i ] = i * 8 ; */) /* ERROR: data_bus [ i ] = i * 8 ; */
    /* ERROR: end */
    // 域选
    assign result = data_bus[3:0];
    // 位选
    assign bit0 = data_bus[0];
endmodule
