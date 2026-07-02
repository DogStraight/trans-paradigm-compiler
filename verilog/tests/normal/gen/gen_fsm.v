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
    always @(posedge clk or negedge rst_n) if (/* ERROR: begin */) /* ERROR: begin */
    if (!rst_n) begin
        state <= IDLE;
    end
    else if (/* ERROR: begin */) /* ERROR: begin */
    state <= next_state;
    /* ERROR: end */
    /* ERROR: end */
    // 次态逻辑
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    case /* ERROR: if ( car_sensor ) */ (state /* ERROR: if ( car_sensor ) */)
        IDLE: if (/* ERROR: begin */) /* ERROR: begin */
    endcase
    next_state = GREEN;
    /* ERROR: else */
    next_state = IDLE;
    /* ERROR: end */
    /* ERROR: GREEN : begin */
    if (timer == 32'd50 /* ERROR: next_state = YELLOW ; */) /* ERROR: next_state = YELLOW ; */ /* ERROR: next_state = YELLOW ; */
    /* ERROR: else */
    next_state = GREEN;
    /* ERROR: end */
    /* ERROR: YELLOW : begin */
    if (timer == 32'd5 /* ERROR: next_state = RED ; */) /* ERROR: next_state = RED ; */ /* ERROR: next_state = RED ; */
    /* ERROR: else */
    next_state = YELLOW;
    /* ERROR: end */
    /* ERROR: RED : begin */
    if (timer == 32'd30 /* ERROR: next_state = IDLE ; */) /* ERROR: next_state = IDLE ; */ /* ERROR: next_state = IDLE ; */
    /* ERROR: else */
    next_state = RED;
    /* ERROR: end */
    /* ERROR: default : next_state = IDLE ; */
    /* ERROR: endcase */
    /* ERROR: end */
    // 计时器
    always @(posedge clk or negedge rst_n) if (/* ERROR: begin */) /* ERROR: begin */
    if (!rst_n /* ERROR: timer <= 32'd0 ; */) /* ERROR: timer <= 32'd0 ; */ /* ERROR: timer <= 32'd0 ; */
    /* ERROR: else if ( state != next_state ) */
    timer <= 32'd0;
    /* ERROR: else */
    timer <= timer + 32'd1;
    /* ERROR: end */
    // 输出
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    case (state)
        IDLE: if (/* ERROR: light = 2'd0 ; */) /* ERROR: light = 2'd0 ; */
        GREEN: if (/* ERROR: light = 2'd1 ; */) /* ERROR: light = 2'd1 ; */
        YELLOW: if (/* ERROR: light = 2'd2 ; */) /* ERROR: light = 2'd2 ; */
        RED: if (/* ERROR: light = 2'd3 ; */) /* ERROR: light = 2'd3 ; */
        default: if (/* ERROR: light = 2'd0 ; */) /* ERROR: light = 2'd0 ; */
    endcase
    /* ERROR: end */
    reg a = 1'b0;
    always @(*) if (/* ERROR: begin */) /* ERROR: begin */
    if (a == 1'b0)
        if (/* ERROR: begin */) /* ERROR: begin */
    else if (/* ERROR: if ( state == GREEN ) begin */) /* ERROR: if ( state == GREEN ) begin */
    if (timer == 32'd25)
        if (/* ERROR: begin */) /* ERROR: begin */
    else if (/* ERROR: if ( car_sensor ) begin */) /* ERROR: if ( car_sensor ) begin */
    a = 1'b1;
    /* ERROR: end */
    /* ERROR: end */
    /* ERROR: end */
    /* ERROR: end else begin */
    a = 1'b0;
    /* ERROR: end */
    /* ERROR: end */
endmodule
