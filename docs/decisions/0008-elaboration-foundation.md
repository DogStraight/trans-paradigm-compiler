# ADR-0008: elaboration 底座（跨文件检查的引擎级前置）

- Status: accepted
- Date: 2026-08-29

## 背景

ADR-0005 决策时明确**拒绝完整 elaboration**（权衡第 ② 条："完整
elaboration/宽度求值——超出范围，与 Verilator 重叠"）。P1.10 主流 lint
机制调研（2026-08-29，三路并行）推翻了这一判断：

- **Verilator/slang/Spyglass 的跨文件检查全是"elaboration 后"视角**——
  端口连接（PINMISSING/PINNOTFOUND/unconnected-port/W287a）、未使用
  （UNUSEDSIGNAL/unused-*）、多驱动（MULTIDRIVEN/W415）、位宽匹配
  （WIDTH/port-width-*）全部依赖"全设计编译 + 实例树展开 + 驱动/负载
  分析"。
- **tpc 现有第一层雏形**（ProjectChecker 的 `module_index` 注册表 +
  `inst_sites` + inst_check W101-W103）只能做"存在性检查"（端口名/参数名
  在不在），做不了"连接关系/驱动负载/层次"——P1.10 核心集合 10 类里
  的未使用类/多驱动/端口完整性/位宽匹配**全做不了**。
- 结论：elaboration 不是与 Verilator 重叠的越界，而是 tpc 跨文件差异化
  检查的**必经底座**。

## 决策

### 1. 三层数据模型（引擎机制，语言无关）

elaboration 底座 = 三层递进数据，全部由 ProjectChecker 构建、经
`_external_extra` 注入插件：

```
层 1  design-unit 注册表 + 依赖拓扑排序
      —— "有哪些模块"（已有雏形：module_index；补依赖序，参照
         HDL Checker database/parsers 思路）
层 2  端口连接关系展开
      —— "模块怎么连"：实例化点连接信号 → 模块端口 → 信号名解析
         （跨文件信号是什么、谁连谁）
层 3  驱动/负载图 + 层次展开
      —— "信号怎么走"：哪个信号被哪个实例驱动、被哪些实例读取
         （UNUSED/UNDRIVEN/MULTIDRIVEN 的地基）；实例树 top→子→孙
         （PINMISSING/PINNOTFOUND 到 MULTIDRIVEN 的必经层）
```

### 2. 配置驱动（延续"语言知识不进代码"）

- 层 1/2/3 的结构提取全部由语言包 `[checker] structure` 协议声明
  （`grammar/<lang>/base/_checker.toml` 扩展字段：端口连接节点形态、
  信号字段名等）——引擎零语言知识，c4/未来 C 语言包同构可用。
- 跨文件检查规则仍走插件（kind 分发 + handler 兜底），handler 拿
  elaboration 数据（连接表/驱动负载图/实例树）做判定。

### 3. 与 ADR-0005 的关系

ADR-0005 的"声明形态 vs 实例化点"比对（inst_check W101-W103）保留为
层 1 之上的存在性检查；本 ADR 补层 2/3，使端口连接/未使用/多驱动等
"elaboration 后"检查成为可能。ADR-0005 拒绝完整 elaboration 的动机
（与 Verilator 重叠）在"差异化检查"语境下不成立——重叠的是机制
（elaboration），差异化的是规则（tpc 配置驱动 + 插件边界）。

### 4. 边界（诚实）

- **不做数值求值**：宽度联动仍只做"参数化 vs 字面量"启发式（ADR-0005
  现状），不做 Verilator 式宽度传播求值——那是独立大工程，P1.10 位宽
  类规则先做"存在性/一致性"层面。
- **不做 CDC**：Spyglass AC_/Ar_ 族（时钟域划分 + 同步结构识别）是独立
  高成本层，远期再评估（ROADMAP 已注记）。

## 权衡

- 代价：ProjectChecker 增 elaboration 阶段（连接展开 + 建图），复杂度
  上升；结构协议配置增字段。
- 换取：P1.10 核心集合 10 类里跨文件类（未使用/多驱动/端口完整性/位宽
  一致性）可落地；tpc"三层捕获错误"能力从语法/浅语义扩展到完整语义层。
- 被拒绝备选：① 引入 Verilator/slang 做 elaboration（违背零依赖 +
  语言知识不进代码）；② 只做"存在性"不做"连接/驱动"（P1.10 跨文件
  核心类做不了）。

## 验证

- pytest：elaboration 层 2/3 单测（连接展开正确性/驱动负载图/实例树）
  + 跨文件端口完整性规则测试（对标 Veryl missing_port/unknown_port +
  Verilator PINMISSING/PINNOTFOUND）。
- 回归：现有 test_checker.py（W101-W103/WC001）不回归；全量 1350+
  pytest 绿；pyright 0。

> Impl: analyzer/checker.py::ProjectChecker（elaboration 阶段：_elaborate_connections
>   层 2 / _build_signal_graph 层 3 / _discover 层 1 递归）
> Impl: analyzer/checker.py::PortConnection（连接展开数据模型）
> Impl: grammar/verilog/base/_checker.toml（结构协议扩展：inst_name/connects/
>   port_name 字段）
> Impl: grammar/verilog/plugins/checks/*（跨文件规则 handler，消费 elaboration 数据）
> Test: tests/engine/analyzer/test_checker.py（TestElaborationConnections 层 2 +
>   TestElaborationSignalGraph 层 3）
