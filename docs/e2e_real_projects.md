# e2e Real 分组测试项目参考

> 目的：为 `tests/e2e/samples/real/` 分组收集**真实工业级 Verilog 源码**作为测试样本，
> 拓宽管线（lexer → linter → parser → analyzer → transform → renderer）的真实文本测试面。
> 本文档记录候选项目、语法面覆盖与测试顺序。2026-08-11 建立。

## 已就位

| 样本 | 来源 | 量级 | 状态 |
|------|------|------|------|
| `picorv32`（`tests/e2e/samples/real/ref/ref_picorv32.v`） | [PicoRV32](https://github.com/cliffordwolf/picorv32) | 2746 行 / 8 模块 / 展开 2705 行 | 全量管线收口：8 模块渲染、post-lint 0、占位符 0、保真度 0.8775 |

picorv32 覆盖：多模块、宏条件编译（25 条件块/14 条件宏）、generate-if 互斥分支、
属性语句（`(* parallel_case *)`）、嵌套 case、三元/拼接/归约/`>>>`/`32'bx`、task、localparam、
裸任务调用（`empty_statement;`）、字符串字面量赋值（`new_ascii_instr = "lui";`）、
嵌套 `ifdef`（`RISCV_FORMAL` 块内嵌 `TESTBUG_003` 等）。

## 推荐候选（按测试顺序）

### 1. SERV — 位串行 RISC-V 核（首选，风格差异大）

- 仓库：https://github.com/olofk/serv （纯 Verilog，ISC 协议，活跃维护）
- 量级：`rtl/serv.v` 约 1300-1500 行（略小于 picorv32）
- 语法面补充：位串行数据通路、`function`、参数化 `generate if`、`$signed`、大 `case` 译码
- 与 picorv32 的差异：串行 vs 并行数据通路，两种写法，压力点不同
- 调试成本：低（单核、结构规整、单文件）

### 2. uart16550 — 经典外设/状态机（补外设面）

- 仓库：https://github.com/freecores/uart16550 （纯 Verilog，2014 停更，代码稳定）
- 量级：约 1000 行（偏小）
- 语法面补充：深度嵌套状态机、大 `case` 分支、参数化波特率、老式 Verilog 风格
- 与 CPU 样本的差异：外设控制逻辑，非数据通路
- 调试成本：低（单模块、无宏/generate 依赖）
- 注意：无 LICENSE 字段，仅作本地测试用

### 3. ZipCPU — 进阶压力（可选，量级大）

- 仓库：https://github.com/ZipCPU/zipcpu （纯 Verilog，活跃维护）
- 量级：rtl 多文件，总源码 5000+ 行（超量级）
- 语法面补充：流水线、Wishbone 总线、**跨模块层次引用**（picorv32 缺失的面）
- 调试成本：偏高（大、多文件），排在 SERV/uart16550 之后

### 4. 人造盲区样本（真实项目覆盖不了的语法）

真实项目基本不会用以下语法，需要人造样本补覆盖：

- `casex` / `casez`
- `for`/`while` 生成循环
- `specify` 块 / UDP / primitive
- 带参宏、`` `include ``
- 结构化过程声明（SV 语法，若后续支持）

## 明确排除

以下项目因语言不兼容（SystemVerilog 或生成语言）不适用：

- **Ibex / NEORV32 / SCR1**（lowRISC 等）— SystemVerilog
- **VexRiscv** — SpinalHDL（Scala）生成，非 Verilog 源
- **Hummingbird E200（蜂鸟）** — SystemVerilog + 开源仓库地址失效（404）

## 测试流程（逐步）

1. 拉取源码 → 提取纯 Verilog 主文件（剔除 testbench/SV 部分）
2. 跑全管线（`tests/e2e/debug_segment_parse.py` 或 `run_pipeline_on_source`）摸底
3. 记录卡点：linter 报错 / parser 停点 / 渲染差异
4. 分类修复：语法缺口（改 grammar） vs 管线缺陷（改核心）——遵守"语言知识外部化"硬约束
5. 修复后入 `tests/e2e/samples/real/ref/`，接线 `run_all_tests.py` real 分组
6. 回归：pytest 全量 + e2e 全组 + 已就位样本不回归

## 现状与下一步

- [x] picorv32 样本就位、跑通全管线
- [x] `run_all_tests.py` real 分组接线（real 组强制 `expand_macros`，参与保真度比较，基线 0.8775）
- [x] 保真度回归守卫 `tests/e2e/test_real_fidelity.py`（7 断言：8 module / post-lint 0 / 无占位符 / 无 WARN / 保真度阈值 / 关键构造保留）
- [ ] SERV 拉取摸底
- [ ] uart16550 拉取摸底
- [ ] ZipCPU 拉取摸底（大样本，优先级最低）
- [ ] 人造盲区样本补语法覆盖
