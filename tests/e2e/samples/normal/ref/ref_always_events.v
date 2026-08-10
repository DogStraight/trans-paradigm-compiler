// ref_always_events.v — always 事件控制四种合法形态
// 贴合 IEEE 1364-2005 A.6.7（event_control）：
//   @(event_expression) / @(*) / @* / @event_identifier

module always_events (
    input  wire clk,
    input  wire rst_n,
    input  wire a,
    input  wire b,
    input  wire d,
    output reg  q,
    output reg  y
);

  // 形态 1: @(event_expression) — 边沿敏感时序逻辑
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      q <= 1'b0;
    else
      q <= d;
  end

  // 形态 2: @(*) — 括号自动敏感（组合逻辑）
  always @(*) begin
    y = a & b;
  end

  // 形态 3: @* — 无括号自动敏感（组合逻辑）
  always @* begin
    y = a ^ b;
  end

  // 形态 4: @event_identifier — 单事件标识符
  always @clk begin
    q <= d;
  end

endmodule
