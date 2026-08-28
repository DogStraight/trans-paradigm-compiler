# Third-Party Sample Attribution

This directory contains Verilog samples from open-source projects,
used as real-world test inputs for the tpc formatter fidelity tests.
These files are **not** part of tpc itself; they belong to their
original authors and projects as noted below.

| Sample | Source | Author | License |
|--------|--------|--------|---------|
| darkriscv | [github.com/marcelosamsoniuk/darkriscv](https://github.com/marcelosamsoniuk/darkriscv) | Marcelo Samsoniuk | BSD 3-Clause |
| picorv32 | [github.com/YosysHQ/picorv32](https://github.com/YosysHQ/picorv32) | Claire Xenia Wolf | ISC |
| serv_top | [github.com/olofk/serv](https://github.com/olofk/serv) | Olof Kindgren | ISC |
| tv80 | [github.com/opencores/tv80](https://github.com/opencores/tv80) | Guy Hutchison | MIT |
| uart / uart_tx / uart_rx | [github.com/alexforencich/verilog-uart](https://github.com/alexforencich/verilog-uart) | Alex Forencich | MIT |
| simcells | YosysHQ/yosys `techlibs/common/simcells.v` | Claire Xenia Wolf | ISC |
| ice40_cells_sim | YosysHQ/yosys `techlibs/ice40/cells_sim.v` | YosysHQ (Claire Xenia Wolf) | ISC（见下注） |

**ice40_cells_sim 许可注**：文件头无版权行，yosys 仓库根 `COPYING` 声明整体 ISC。

**语料边界注**：
- `ref_ice40_cells_sim.v` 使用**默认配置**（不预定义 NO_ICE40_DEFAULT_ASSIGNMENTS）：
  端口默认值宏（`input NAME `ICE40_DEFAULT_ASSIGNMENT_1`，body=`= 1'b1`）走
  inline+body 锚还原（M1，2026-08-28）——`tests/e2e/test_real_corpus.py` 的
  per-file predefined 为空。
- yosys `techlibs/common/techmap.v` 已排除：`$demux` 类 yosys 内部 cell 名、
  `(2**i)'b0` 表达式宽度字面量属 yosys 内部/SV 形态，非 2005/1800 Annex A
  合法输入（sv-parser 同样拒绝）；其多目标 assign 用法见 test_2005_batch7.py。

Each sample file retains its original copyright header. The full license
texts are reproduced below for reference.

---

## BSD 3-Clause (darkriscv)

Copyright (c) 2018, Marcelo Samsoniuk
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED.

## ISC (picorv32, serv_top)

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS.

## MIT (tv80)

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
