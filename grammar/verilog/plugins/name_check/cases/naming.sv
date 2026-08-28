// 注释驱动测试样例（ruleid: 必须命中 / ok: 不得命中）
// 扫描 grammar/verilog/plugins/name_check/cases/*.sv 由
// test_name_convention.py::TestCommentDrivenCases 驱动（零代码测试）。
module m (
  // ok: NC005
  input wire good_port,
  // ruleid: NC005
  input wire BAD_PORT,
  output wire ok_out
);
  // ok: NC001
  wire good_net;
  // ruleid: NC003
  wire BAD_NET;
  // ruleid: NC004
  reg BAD_REG;
endmodule

module Mux2x1; // ruleid: NC001
endmodule
