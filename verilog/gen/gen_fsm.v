module traffic_light (
    input  wire clk,
    input  wire rst_n,
    input  wire car_sensor,
    output reg  [1:0] light
);

    reg [1:0] state;
    reg [1:0] next_state;
    reg [31:0] timer;
    localparam IDLE = 2'd0,;
    localparam GREEN = 2'd1,;
    localparam YELLOW = 2'd2,;
    localparam RED = 2'd3,;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
        end else begin
            state <= next_state;
        end
    end
    always @(*) begin
        case (state)
            IDLE: begin
                if (car_sensor)
                    next_state = GREEN;
                else
                    next_state = IDLE;
            end
            GREEN: begin
                if (timer == 32'd50)
                    next_state = YELLOW;
                else
                    next_state = GREEN;
            end
            YELLOW: begin
                if (timer == 32'd5)
                    next_state = RED;
                else
                    next_state = YELLOW;
            end
            RED: begin
                if (timer == 32'd30)
                    next_state = IDLE;
                else
                    next_state = RED;
            end
            default: next_state = IDLE;
        endcase
    end
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            timer <= 32'd0;
        else if (state != next_state)
            timer <= 32'd0;
        else
            timer <= timer + 32'd1;
    end
    always @(*) begin
        case (state)
            IDLE: light = 2'd0;
            GREEN: light = 2'd1;
            YELLOW: light = 2'd2;
            RED: light = 2'd3;
            default: light = 2'd0;
        endcase
    end

endmodule
