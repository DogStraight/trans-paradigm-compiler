`define MAX(a, b) ((a) > (b) ? (a) : (b))

module m;
    wire [7:0] x, y, z;
    assign z = `MAX(x, y);
endmodule
