// edge: 深嵌套控制流 + 多声明行 + 三元链
module m(input clk, input [7:0] a, input [7:0] b);
    reg [1:0] state, next;
    wire [7:0] y, z;

    always @(posedge clk) begin
        if (a[0]) begin
            if (b[1]) begin
                case (state)
                    2'b00: next = 2'b01;
                    2'b01: next = 2'b10;
                    default: next = 2'b00;
                endcase
            end else begin
                next = state;
            end
        end else begin
            next = a[3] ? b[2] ? 2'b11 : 2'b10 : 2'b01;
        end
    end

    assign y = a & b;
    assign z = a | b;
endmodule
