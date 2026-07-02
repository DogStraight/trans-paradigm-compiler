// Test: 数组声明 + 数组元素访问 + 域选
module array_test();

    reg [7:0] mem[0:15];
    reg [31:0] data_bus[0:7];
    integer i;
    always @ ( posedge clk ) begin
    if ( we )
    mem[addr] <= data_in;
    data_out <= mem[addr];
    end
    always @ ( * ) begin
    for (i = 0; i < 8; i = i + 1) 
        data_bus[i] = i * 8;
    end
    // 域选
    assign result = data_bus[3:0];
    // 位选
    assign bit0 = data_bus[0];
endmodule
