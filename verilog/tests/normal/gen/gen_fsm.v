// Test 2: 有限状态机 — 三段式
// 功能: 简单交通灯控制器
module traffic_light(
    input wire clk,
    input wire rst_n,
    input wire car_sensor,
    output reg [1:0] light = 2'b0);

    reg [1:0] state;
    reg [1:0] next_state;
    reg [31:0] timer = 32'd0;
    // 状态编码
    localparam IDLE = 2'd0;
    localparam GREEN = 2'd1;
    localparam YELLOW = 2'd2;
    localparam RED = 2'd3;
    // 状态寄存器
    always @ ( posedge clk or negedge rst_n ) begin
    if ( ! rst_n ) begin
    state <= IDLE;
    end else begin
    state <= next_state;
    end
    end
    // 次态逻辑
    always @ ( * ) begin
    case ( state )
    IDLE : begin
    if ( car_sensor )
    next_state = GREEN;
    else
    next_state = IDLE;
    end
    GREEN : begin
    if ( timer == 32'd50 )
    next_state = YELLOW;
    else
    next_state = GREEN;
    end
    YELLOW : begin
    if ( timer == 32'd5 )
    next_state = RED;
    else
    next_state = YELLOW;
    end
    RED : begin
    if ( timer == 32'd30 )
    next_state = IDLE;
    else
    next_state = RED;
    end
    default : next_state = IDLE ;
    endcase
    end
    // 计时器
    always @ ( posedge clk or negedge rst_n ) begin
    if ( ! rst_n )
    timer <= 32'd0;
    else if ( state != next_state )
    timer <= 32'd0;
    else
    timer <= timer + 32'd1;
    end
    // 输出
    always @ ( * ) begin
    case (state)
        IDLE: light = 2'd0;
        GREEN: light = 2'd1;
        YELLOW: light = 2'd2;
        RED: light = 2'd3;
        default: light = 2'd0;
    endcase
    end
    reg a = 1'b0;
    always @(*) begin
        if ( a == 1'b0 ) begin
        if ( state == GREEN ) begin
        if ( timer == 32'd25 ) begin
        if ( car_sensor ) begin
        a = 1'b1;
    end
    
    end
    end else begin
    a = 1'b0;
    end
    end
endmodule
