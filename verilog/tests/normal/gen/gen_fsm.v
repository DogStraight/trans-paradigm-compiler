// Test 2: 有限状态机 — 三段式
// 功能: 简单交通灯控制器
module traffic_light (
input wire clk
,
input wire rst_n
,
input wire car_sensor
,
output reg [1:0] light = 2'b0
) ;
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