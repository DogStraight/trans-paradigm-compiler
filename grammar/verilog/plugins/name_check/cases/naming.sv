// 注释驱动测试样例（ruleid: 必须命中 / ok: 不得命中）
// 扫描 grammar/verilog/plugins/name_check/cases/*.sv 由
// test_name_convention.py::TestCommentDrivenCases 驱动（零代码测试）。
// 文件名 naming.sv → 主模块命名 naming（NC011 模块名-文件名一致）。
module naming (
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

// 第二个模块（同文件）：文件命名已由 naming 匹配，Mux2x1 不误报 NC011
// （多模块同文件防御）——只断言 NC001 命名违规。
module Mux2x1; // ruleid: NC001
endmodule
