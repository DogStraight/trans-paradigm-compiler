// Test: +: 和 -: 范围选择
module plusrange_test();

    reg [31:0] data;
    always @(*) begin
        result = data[addr*8+:8];
        result2 = data[addr*8-:8];
        result3 = data[base+:width];
        result4 = data[base-:width];
    end
    
endmodule
