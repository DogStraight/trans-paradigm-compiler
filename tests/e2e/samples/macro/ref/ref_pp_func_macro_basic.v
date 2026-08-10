`define MIN(a, b) ((a) < (b) ? (a) : (b))

module m;
    wire [7:0] x, y, z;
    assign z = `MIN(x, y);
endmodule
