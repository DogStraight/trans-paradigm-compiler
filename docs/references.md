# 参考与借鉴项目

> 本文件记录影响 tpc 设计的参考项目及其借鉴点（设计来源可追溯）。
> 与 `tests/e2e/samples/real/CREDITS.md`（第三方样本署名）互补：
> 前者管"设计来源"，后者管"代码来源"。

## 收录标准与格式

**收录范围**：影响 tpc 设计的 parser/编译器/格式化/IR/语言工作台/transpiler/
provenance 类项目；含"同龄人"（同期同理念项目，作为参照系）。

**颗粒度两级**：
- **索引级**（下表）：一行——项目 | 关系 | 一句话价值总结（链接在项目名上）
- **调研级**（下方"深调研"节）：定位 → 管线结构逐阶段对比（列表）→ 亮点单独
  说明 → 可实现性评估（可做/不做及成本）；仅对深度参考项目展开

**关系取值**：`深度参考`（有深调研节）/ `架构对比`（理念或组织相似，无详情节）/
`设计参考`（局部借鉴）/ `概念参考`（理念启发）。

**基调**：见贤思齐——先讲对方做得好、值得学的地方；差异用"各有取舍，非优劣"
表述；不拉踩开源作者。

**新增条目检查**：是否属于上述收录范围？写索引行（统一 3 列）→ 值得深调研则
加详情节并标 `深度参考` → 检查类别小节是否合适，避免漏类（如 transpiler 类
曾漏 sv2v）。

## 索引（按类别）

### 解析引擎与语法技术

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [DmitrySoshnikov/syntax](https://github.com/DmitrySoshnikov/syntax) | 设计参考 | "语言无关的语法规则作为独立资产"的可行性验证、运算符优先级声明、多语言输出模式 |
| [sv-parser](https://github.com/dalance/sv-parser) | 深度参考 | dalance 的 IEEE 1800-2017 全量 SV parser 库（svlint/svls 地基）；CST 节点 ↔ nom 组合子章节镜像 + build.rs 生成节点枚举 + nom 扩展全家桶（详见深调研） |
| [Lark](https://github.com/lark-parser/lark) | 概念参考 | Earley 与递归下降的取舍分析、grammar 格式对比 |
| [Grammar-Kit](https://github.com/JetBrains/Grammar-Kit) | 设计参考 | Pin 机制（未采用，启发了 end_case + 回溯组合设计） |
| [ANTLR](https://github.com/antlr/antlr4) | 概念参考 | 工业级 parser generator 的定位差异 |
| [Tree-sitter](https://github.com/tree-sitter/tree-sitter) | 概念参考 | 增量解析与容错解析的思路 |
| [INRIA Syntax](https://github.com/moosetechnology/syntax) | 设计参考 | C/Fortran 领域的配置驱动解析原型 |
| Parser Combinators ([pyparsing](https://github.com/pyparsing/pyparsing) / [nom](https://github.com/rust-bakery/nom)) | 概念参考 | 语法即代码 vs 配置驱动；Scannerless vs 管线分离；无渲染 vs Doc IR |
| [parlex](https://github.com/ikhomyakov/parlex) | 设计参考 | SLR(1) 运行时歧义消解对 end_case 的启发 |
| [ModelCC](https://modelcc.ikor.org/) | 设计参考 | 模型驱动 parser generator；`@Priority`/`@Associativity` 声明式消歧验证了声明式配置方向 |
| [MoonBit](https://www.moonbitlang.com/) | 概念参考 | 双轨解析（Menhir LR + 手写递归下降并行）；sync 栈错误恢复（不适用：sync 栈是语法知识，配置驱动引擎无法自动推导） |
| [RADLR](https://github.com/acweathersby/radlr) | 设计参考 | parser 分类报告（LL/RD/RAD 等）及算法复杂度评估（metrics 概念用于调试输出） |
| [Parsek](https://github.com/anptrs/parsek) | 概念参考 | 组合子+FSM 混合模式（词法 FSM + 解析递归下降） |
| [parsejoy](https://github.com/adewes/parsejoy) | 概念参考 | YAML 语法即数据（实验性，未完成） |
| [Ohm](https://github.com/ohmjs/ohm) | 深度参考 | JS PEG + 语法/语义完全分离 + 语义惰性求值 + 增量解析（packrat memo 区间失效）——P3.4 增量 check 的现成参照（详见深调研） |
| [DHParser](https://gitlab.lrz.de/badw-it/DHParser) | 概念参考 | 完整 left-recursion 支持、测试驱动语法开发、声明式 AST 变换；错误恢复方案不同（反向解析器 vs post-mortem） |
| [Veryl](https://github.com/veryl-lang/veryl) | 设计参考 | SystemVerilog 现代超集 HDL（Rust，1026★，2022 起活跃）：语法简化 + 可综合保证 + 类型化 clock/reset + 转译保真——HDL 语法设计的直接参照（详见深调研） |
| [pyverilog](https://github.com/PyHDI/Pyverilog) | 概念参考 | Takamaeda-Yamazaki（日本学者）的 Python HDL 工具包：PLY（Lex/Yacc 风格）LALR 文法声明做 Verilog 解析——"语法即声明、Verilog 工具不必手写解析器"的早期代表（与 Veryl 同作者国别、同 HDL 工具窄域；设计来源追溯见深调研「路线亲缘」） |

### 格式化与渲染

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [cmake-format](https://github.com/cheshirekow/cmakelang) | 设计参考 | 多通道递进布局算法、Layout Tree 与 Syntax Tree 并行模式、注释重排、量化布局拒绝准则 |
| [Prettier](https://github.com/prettier/prettier) | 概念参考 | "格式化即正确"理念、before/after 代码对比 |
| [wadler-lindig](https://github.com/patrick-kidger/wadler-lindig) | 概念参考 | Wadler-Lindig Doc IR 算法（Renderer 的理论源头） |
| [topiary](https://github.com/topiary/topiary) | 概念参考 | tree-sitter 查询驱动的声明式 formatter（纯规则不写代码）；capture 注解到不了跨行对齐——"封闭式"粒度极限的实证 |
| [dprint](https://github.com/dprint/dprint) | 概念参考 | 配置驱动插件平台（Rust/wasm 插件）；"配置是选项非布局规则"，语言插件仍需手写 printer |
| [verible-verilog-format](https://github.com/chipsalliance/verible) | 架构对比 | Google Verilog/SystemVerilog 官方 formatter（token 流 + 布局决策 + 注释锚定）；tpc 差分测试已带其 exe，是高精度目标参照（详见深调研） |
| [istyle-verilog-formatter](https://github.com/thomasrussellmurphy/istyle-verilog-formatter) | 概念参考 | 独立开源 Verilog formatter（C++，~187★，2026 仍活跃）——Astyle 式缩进风格引擎，验证"格式即风格选项"路线 |
| [verilog-format](https://github.com/ericsonj/verilog-format) | 概念参考 | Java 独立 Verilog formatter（~207★，2019 起维护）：`-s verilog-format.properties` 属性文件驱动选项——"配置是选项非布局规则"的另一实证 |

### 静态检查（HDL lint）

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [verible-verilog-lint](https://github.com/chipsalliance/verible) | 设计参考 | 规则表 + rule-sets 配置 + 规则描述输出（`--print_rule_descriptions`）；与 formatter 同仓库，规则/诊断工程化范本（详见深调研） |
| [Verilator `--lint-only`](https://github.com/verilator/verilator) | 设计参考 | W 码警告体系（200+ 条）+ `lint_off`/`lint_on` 注释对 suppress——语义级 lint 事实标准（详见深调研） |
| [slang `--lint-only`](https://github.com/MikePopoloski/slang) | 设计参考 | diagnostics severity 体系 + waiver 文件；unused/suspicious 规则族（详见深调研） |
| [svlint](https://github.com/dalance/svlint) | 深度参考 | 纯规则化 lint（190+ 规则，`.svlint.toml` 逐条 severity）——与 tpc linter 形态最接近；规则工程化闭环（自动登记/测试/文档）范本（详见深调研） |
| [svls](https://github.com/dalance/svls) | 设计参考 | svlint 的 LSP 封装（3 源文件）——"检查器 → LSP"库级复用最薄形态（详见深调研） |
| [flexlint](https://github.com/dalance/flexlint) | 设计参考 | 正则规则 lint（规则 = TOML 正则四元组，无 parser）——第三种 lint 形态与位置断言（详见深调研） |
| [hdl_checker](https://github.com/suoto/hdl_checker) | 概念参考 | "封装既有 HDL 工具做 LSP 诊断"——pylance 式使用场景的架构参照（详见深调研） |
| [SpyGlass](https://www.synopsys.com/verification/static-verification/spyglass-rtl-datasheet.html)（Synopsys，商业） | 设计参考 | 业界 RTL lint 天花板：Rule→Goal→Sub-Methodology 三层规则组织 + SGDC 约束压误报 + waiver 体系（详见深调研"第三路"） |

### 商业 EDA 工具链（方法论参照）

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [Synopsys](https://www.synopsys.com/)（VCS / Design Compiler / SDC） | 概念参考 | 商业 EDA 巨头 Verilog 工具链方法论：VCS 编译型前端三步法、DC elaborate 跨文件语义分析、SDC 声明式约束成行业接口标准——"约束/配置即数据"的工业级先例（详见深调研） |

### IR 与编译管线

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [Taichi](https://github.com/taichi-dev/taichi) | 概念参考 | 多级 IR 设计（FrontendIR → LowerAST → SSA IR）的 lower_ast pass 与 normalizer 职责类似 |
| [MLIR ODS (llvm/llvm-project)](https://github.com/llvm/llvm-project) | 概念参考 | 配置驱动 Operation 定义体系（TableGen .td），自动生成 C++ 构造器/验证器/序列化 |
| [CIRCT (llvm/circt)](https://github.com/llvm/circt) | 概念参考 | MLIR-based 硬件编译器，FIRRTL→HW→SV→Verilog 多级下降管线 |
| [ClangIR / CIR (llvm/llvm-project)](https://clang.llvm.org/docs/ClangIR.html) | 概念参考 | Clang 的 MLIR-based 中级 IR，使用 ODS 定义所有操作 |
| [VAST](https://github.com/trailofbits/vast) | 深度参考 | 程序分析向的 MLIR 塔式 IR 管线；Tower 机制（每个 pass 后克隆模块 + 记录转换步骤 + 位置反向链接）是 provenance 链的工程化范本（详见深调研） |
| [lyra](https://github.com/hankhsu1996/lyra) | 深度参考 | SystemVerilog 仿真工具链（C++/Bazel，复用 slang AST），同期活跃的同龄人；多级 IR + 927 case 测试组织可借鉴（详见深调研） |

### 语言工作台与 DSL

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [textX](https://github.com/textX/textX) | 概念参考 | Python 生态的 DSL 工作台，配置驱动理念 |
| [Spoofax](https://github.com/metaborg/spoofax) | 概念参考 | 语言工作台（Java/Eclipse），编译期生成 vs 运行时 TOML；Statix scope graph 约束系统 |
| [Langium](https://github.com/eclipse-langium/langium) | 设计参考 | grammar DSL 直接生成 AST 类型定义的理念（从 TOML production 推导类型定义） |
| [Xtext](https://github.com/eclipse-xtext/xtext) | 概念参考 | 语法 DSL 生成 AST 类型定义；Maven 复杂度验证了零依赖方向 |
| [JetBrains MPS](https://github.com/JetBrains/MPS) | 概念参考 | 重量级语言工作台（项目化 DSL + 多目标生成）——天花板参照 |
| [ldtk](https://github.com/Terran-One/ldtk) | 概念参考 | TS 模块化语言开发工具包 |
| [desugar](https://github.com/michaelmillar/desugar) | 概念参考 | 逐步 pass 可视化（编译器模拟器方向） |
| [rascal](https://github.com/usethesource/rascal) | 深度参考 | 元编程语言：完整 REPL + GLR 解析 + 具体语法模式匹配（详见深调研） |
| [Koine](https://github.com/chrsbats/koine) | 深度参考 | 语法即数据（YAML/JSON/TOML）+ 管道式 + subgrammar 多文件组织；聚焦快速 DSL 原型（详见深调研） |

### 源到源转换（transpiler）

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [sv2v](https://github.com/zachjs/sv2v) | 深度参考 | SystemVerilog→Verilog 转换器（Haskell，748★）；50 个转换 pass 每个一个文件的组织 + 1046 测试用例；作为源到源编译器却未被 awesome-transpilers 收录（详见深调研） |

### 增量解析与 provenance

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [cairn](https://github.com/eurisko-info-lab/cairn) | 深度参考 | 语言 = Fragment 片段组合 + 内容寻址；双向文法（一个 GrammarSpec 同时生成 parse+print）（详见深调研） |
| [lvca](https://github.com/joelburget/lvca) | 深度参考 | OCaml provenance：`Provenance.t`（每个节点带 range）是一等公民（详见深调研） |

### 工程组织与后端抽象

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [Foundry](https://github.com/foundry-rs/foundry) | 架构对比 | Ethereum 开发工具链（Rust，10k+★）；模块化切片（forge/cast/anvil/chisel 独立组件）与碎片化 changelog 是工程组织的范本（详见深调研） |
| [vbcc](https://github.com/Leffmann/vbcc) | 深度参考 | 1989 年起的可移植 C 编译器，13 个目标后端；machines/ 目录一个后端一个目录的极简组织（详见深调研） |

## 深调研（详情）

### Veryl（Rust）— SystemVerilog 现代超集 HDL（2026-08 调研，agent-reach 采集）

- 本地源码镜像：`E:\research\veryl`（主仓库）+ `E:\research\veryl-doc`（官方 book 源），
  由 `E:\research\README.md` 索引；后续查阅/追更直接读本地，不重复 clone
- 定位：dalance（svlint 作者）的 HDL 语言设计——SystemVerilog 语法子集 + 语法简化，
  Veryl 源码转译回**高可读 SV**（transpiler 而非新仿真生态）；1026★，2022 起活跃，
  HN 主帖 76 points/45 comments（2024-03），2025-2026 连续版本发布（0.16.x）
- 管线结构：Veryl 源码 → parser（Rust）→ 语义检查 → SV 代码生成；配套 verylup
  （工具链安装器）/ std（标准库）/ doc（文档仓库）/ tree-sitter-veryl（编辑器语法）；
  管线架构深读（五段分析/增量缓存/emitter 双模式/aligner PadKind）见下文深读节
- **语法设计亮点**（对 tpc 的 verilog 语言包最有参照价值的部分）：
  - 🔥 **类型化 clock/reset**（`clock`/`reset`/`clock_posedge`/`reset_async_low` 等 8 变体）：
    极性/同步性从语法中剥离，由**构建期配置**指定——同一代码可生成 ASIC 负异步复位
    与 FPGA 正同步复位两版。tpc 已有 port roles + `invert`（`slave : invert master`），
    Veryl 是"角色系统进类型系统"的更强形态：clock/reset 是类型而非 role
  - 💡 **方向反转内建**：`clock_posedge` 是 `clock` + 极性配置的组合——与 tpc
    `invert master` 的"角色派生"理念同构，但 Veryl 落在类型声明位而非显式变换
  - 💡 **default clock/reset**：单时钟模块可省略连接（`always_ff {}` 无参数）——
    显式性默认值化的思路，tpc 的 opt 省略可参考其"语境默认"而非仅"空省略"
  - 💡 **语法简化清单**（trailing comma / `if`/`case` 表达式 / `repeat` 连接 /
    `msb` 记法 / `let` 语句 / `<>` 接口连接 / range 记法 `..` vs `..=`）：
    "常见惯用法有专用语法"的设计原则——tpc 语法增强的候选方向清单
- **与 tpc 的差异**（各有取舍，非优劣）：

| 维度 | Veryl | tpc |
|------|-------|-----|
| 定位 | 新 HDL 语言（自己设计语法） | 语言流水线（语法即 TOML 资产） |
| 语法来源 | Rust 手写 parser + 语义检查 | 引擎通用 + grammar/verilog TOML |
| 语义保证 | 可综合保证 + CDC 检查 + 类型系统 | 分析器扩展点（primitive 配置） |
| 产出 | 转译 SV（保真、可读） | 格式化/检查为主（非转译语言） |

- **可实现性评估**：
  - 🔥 **可做（低成本）**：trailing comma 端口列表（列表 join 已在 join 原语层，
    `[PortList.renderer.layout]` 补尾逗号规则即可）；`msb`/`lsb` 记法（Verilog
    语法糖，TOML 表达式规则可声明）
  - 💡 **可做（中成本）**：clock/reset 类型进 verilog 语言包（`[id.keyword]` +
    port role 扩展 + 分析器检查接线一致性）——tpc 的 port roles 已验证方向，
    Veryl 提供"类型化"的下一步形态
  - 📌 **不做**：CDC 检查 / 综合保证 / 内建仿真（Veryl 是完整工具链，tpc 聚焦
    语法流水线本身；其 CDC 语义检查可在 analyzer primitive 层借鉴，但属大 feature）
  - 📌 **观察**：Veryl 的"构建期配置驱动代码生成"（clock 极性）与 tpc 的
    "配置驱动渲染"哲学同源——都是"形态与语义解耦"，路径不同（语言设计 vs 引擎）

- **管线架构深读**（2026-08 二探，clone 主仓库读源码）——"tpc 管线拟态 Veryl"的对照：

  Veryl 分析管线（`pipeline.rs`，build/check/test/publish/doc/dump/synth 共用）：
  ```
  parse → analyze_pass1 → analyze_post_pass1 → analyze_pass2 → analyze_post_pass2
  ```
  - **五段分析**：pass1 建符号/类型表 → post_pass1 全局检查（unused 等）→
    pass2 逐文件 IR/代码生成 → post_pass2 跨文件后检查（组合环检测等）——
    与 tpc 的 lint/parse/analyze/transform/render 序列是不同切法（Veryl 按
    "语义阶段"切，tpc 按"语法阶段"切）
  - 🔥 **内容寻址增量缓存**（`incremental.rs` + `cache` crate）：`.build/cache`
    下 `manifest.toml` + 每源文件一个 blob（pass1 片段）；keyed on **二进制
    指纹 + 构建配置**（工具链/配置变更整体失效）；`try_restore` 命中跳过
    pass2/emit；**错误文件永不缓存**，warm 跑只回放警告（`Cached` diag 与
    fresh diag 按 key 去重，`drop_cached_duplicates`）——tpc run_all 的
    fidelity 缓存是"只升不降"，Veryl 是"内容寻址 + 语义去重"，更精确
  - 🔥 **emitter 双模式**（`emitter.rs`）：`Mode::Align`（pass1 喂 token 给
    aligner 算列 padding）→ `Mode::Build`（pass2 建 Doc IR 树 + render）——
    与 tpc 世界 B column_align 两遍式**同构**；且 Veryl 也用 `veryl_pretty::doc::Doc`
    + `render_with_anchors`（注释锚定）——Doc IR + 对齐 + 注释锚定三者组合
    与 tpc 渲染器设计撞车，验证了方向
  - 🔥 **aligner PadKind 三态**（`aligner/src/lib.rs`）：`Always`（恒输出，
    计入 fits_flat）/ `IfBreak`（布局组断行才输出）/ `IfFlat`（flat 才输出，
    超宽可强制断行）——**对齐与 Wadler-Lindig fits/break 语义融合**：对齐
    padding 不是独立的"列对齐后处理"，而是参与布局决策的 Doc 一等公民。
    tpc 世界 B column_align 目前是"渲染后对齐"（曾破坏 fits 判定），Veryl
    是"对齐进 Doc IR"——这是 tpc 对齐与 Doc IR 融合的参考形态
  - 💡 **build --check 差分**（`cmd_build.rs`）：`output != emitter.as_str()` 时
    `print_diff` 失败退出——与 tpc 幂等/差分门禁同构（tpc 是 fidelity 度量，
    Veryl 是字节 diff）；bundle target 用 temp dir 暂存后整体比对
  - 💡 **filelist 拓扑排序**（`sort_filelist`）：`type_dag::toposort()` 按符号
    依赖图排序输出文件清单——tpc 无此概念（单文件管线），多文件场景可参考
  - 📌 **sourcemap**：Veryl→SV 位置映射（`sourcemap` crate）——tpc Node 缺
    token span 的前置（lvca 的 provenance 也指向同一缺口）
  - 📌 **simulator/cosim/synthesizer**（内建仿真/协同仿真/综合）：完整工具链
    范畴，tpc 不做（README 已声明），仅作路线观察

- **渲染层深读**（2026-08 三探，`veryl_pretty`/`aligner`/`emitter` 源码）——
  "tpc 渲染缺口闭环"的对照：

  **Veryl Doc 原语集**（`crates/pretty/src/doc.rs`，Wadler 家族 + 9 扩展）：
  ```
  Nil/Text/Concat/Indent/Group          ← Wadler 核心（与 tpc 同源）
  ForceFlat / Line / Hardline           ← tpc 有等价物（Union flat / Break）
  DedentHardline(level)                 ← tpc 无：硬换行 + 剥 level*width 尾随空格
  Comments(CommentDoc[])                ← tpc 半有（LineSuffix 行尾注释）
  IfBreak(text) / IfBreakPad(w)         ← tpc 无：broken 模式才输出（0 计 fits）
  Pad(w) / IfFlatPad(w)                 ← tpc 无：对齐 padding 进 Doc 参与 fits
  Anchored(text, src_line, src_col)     ← tpc 无：sourcemap 锚点（P3.1 前置）
  ```

  **缺口闭环评估**（对 tpc 渲染层的价值分级）：
  - 🔥 **Pad/IfBreakPad/IfFlatPad 三件套**（`doc.rs` 三行声明 + `render.rs` 各
    几行渲染）——"对齐进 Doc IR"的最小实现：`Doc::Pad` 无条件输出且计入
    `fits_flat`，`IfBreakPad` 仅 broken 输出（断行后补对齐），`IfFlatPad`
    仅 flat 输出且超宽可强制断行。tpc 世界 B column_align 是"渲染后对齐"
    （曾破坏 fits 判定、被迫回滚 join 改法），这三件套是"对齐参与布局
    决策"的参考形态——**低成本高价值，建议 TODO**
  - 🔥 **fits_flat 带外层 continuation**（`render.rs::fits_flat` 从 outer stack
    拷贝 `work` 继续算）——解决"fill 模式邻居项各自声明 flat、组合行
    溢出"（tpc `_fits` 只看单 doc 第一行，正是 tpc wrap 调研记过的坑）——
    **tpc `_fill`/`_fits` 的直接参考实现**
  - 💡 **DedentHardline**：对齐 padding 不残留行尾（tpc 对齐后处理需要
    strip 尾随空格的场景，Veryl 用 Doc 原语表达）
  - 💡 **两遍式对齐管线**（`emitter::emit` 同一 walker 跑 Align→Build 两遍）：
    Align 遍按 **18 种语义角色**（IDENTIFIER/TYPE/EXPRESSION/WIDTH/DIRECTION
    等）收集 `{Location: (max_width - width, PadKind)}`，Build 遍
    `process_token` 查表注入 Pad——tpc 世界 B column_align 按列组织，
    Veryl 按**角色分组 + 每组独立 max_width**，且 emitter 的
    `align_start(kind)/align_finish(kind)` 成对包裹 emit 片段——配置化时
    可把"角色→列"映射声明进布局 TOML
  - 💡 **CommentDoc 进 Doc**（`render.rs::render_comments`）：注释带
    leading_newlines/锚点，`is_line_comment` 终止当前行（参与 fits）——
    tpc LineSuffix 只覆盖行尾注释，Veryl 把注释做成完整 Doc 公民
  - 📌 **strip_trailing_whitespace 开关**：build --check 时关掉保字节一致
    （tpc fidelity 差分同理）；Anchored → sourcemap（P3.1 前置）

- **tpc 注释节点模型（设计来源，2026-08 讨论 + 落地）**——与 Veryl 注释机制的对照：
  - 设计决策（用户参与）：注释是"间隙实体"（token 流中两 token 之间），有挂点
    （行尾）attachment、无挂点（token 间隙/游离）需位置。挂树方案（attachment 化）
    覆盖不了无挂载点注释；Veryl 的 token 级附着（`TerminalToken: Token Comments`）
    解决静态间隙但不解决结构重写；**变换路径注释是语义归属问题**（注释属于概念
    如 impl/端口组），答案在变换语义里（migrate_comments 声明迁移目标），不在
    位置机制里
  - 落地形态：注释 = AST 一等节点 + 槽位约定（leading 独立行 / inline 同行前置 /
    trailing 行尾锚定 / inline_after token 标注），生产方（parser/变换插件）负责
    语义归属，消费方（renderer）按槽位渲染——与 Veryl "注释进 Doc 公民"（CommentDoc
    + leading_newlines）同理念、不同载体（tpc 挂节点槽位，Veryl 挂 token 流）
  - 时域/频域类比（用户启发）：字符流 = 时域（行号/token 位置，漂移），AST/结构
    路径 = 频域（结构序，不漂移）；渲染 = 调制、解析 = 解调。注释治本 = 结构
    附着 + 结构序渲染（tpc 槽位约定即结构序；restore 行号回插是时域兜底，双轨
    不双份）

- **SV 覆盖边界（2026-08-27 追读，emitter 发射面 + embed 机制）**——Veryl 不映射
  完整 SV，只覆盖"现代可综合设计的关键子集"，超出部分透传：
  - 语言特性全集（language_reference 20 项）全是设计面：module/interface/modport/
    package/import/enum/struct/typedef/always_ff/always_comb/generics/clock domain/
    visibility——**无 class、无 assertion/coverage/randomize、无门级原语/UDP/
    specify**（emitter.rs 无这些 SV 构造的发射代码）
  - **embed 透传机制**：`embed (inline) sv{{{{ ... }}}}` 原样嵌入 SV 代码块 +
    `{ident}` 标识符插值，Veryl 对嵌入内容**不解析不检查**（语义错误表只查
    embed 声明本身的合法性：invalid_embed/unknown_embed_lang/unknown_embed_way）
    ——"超出关键子集的 SV"是透明区域，边界画在 embed 声明上
  - emitter 的发射智能（always_ff 隐式事件列表推导/reset 检测、modport 连接
    展开表、package 前缀抑制、`pkg::*` 成员遮蔽处理）说明 Veryl 的重心在
    "生成正确 SV"而非"覆盖 SV 全集"
  - **对 tpc 的启示**：
    - 💡 **生态验证了边界策略**：连"专职 SV 转译"的 Veryl 都不做 SV 全量映射，
      tpc 的"2005 全量 + 高频 SV 构造子集"边界成立；Veryl 特性集即 sv_compat
      插件的现成构造清单（module/interface/modport/package/enum/struct/
      always_ff/always_comb——与 sv-parser 83 个 CST 文件相比是刻意裁剪的关键面）
    - 💡 **embed 与 tpc 黑盒同构**：Veryl 对超出部分"透传 + 边界检查"；tpc 解析
      输入不能透传，但 linter 已有表达式黑盒/块黑盒（skip）机制——sv_compat
      遇 SVA/class 可"黑盒跳过 + 定位诊断"，哲学同源（透明区域 + 边界检查），
      tpc 侧无需 Veryl 的发射智能，边界更薄
    - 📌 **发射面 ≠ 解析面**：Veryl 覆盖 SV 的"发射面"（生成哪些构造）与 tpc
      需要的"解析面"（接受哪些构造）不同维——tpc 的 sv_compat 只需解析面
      （parse/format/lint），不需要 Veryl 的 modport 展开/事件列表推导等发射智能

- **路线亲缘（2026-08-29 收束）**：与 Veryl 的整体定位对比——"Veryl 在单科目
  拿 95 分（SV 语义深度/性能），tpc 尽可能在所有科目拿 80 分（语法资产化/
  多语言/保真还原/配置驱动形态/差分验证）"。80 分科目多是"机制"而非"积累"
  （语义深度 60-70 分是规则积累量小，可填规则补涨；Veryl 的 95 分绑定
  dalance 个人 Rust 语义工程，不可复制也不可迁移）。关键性质：**tpc 的 80 分
  绑定在配置资产 + 验证纪律上，可复制、可演进、可被模型协作放大**——与
  "单科 95 绑定专才"是不同性质的可演进性。
- **共同启发源（2026-08-29）**：tpc 与 Veryl 的路线源头可追溯到
  [pyverilog](https://github.com/PyHDI/Pyverilog)（Takamaeda-Yamazaki，日本
  学者）：PLY（Lex/Yacc 风格）LALR 文法声明做 Verilog 解析——"语法即声明、
  Verilog 工具不必手写解析器"的早期代表。同一颗"声明式语法"种子分叉：
  Veryl 走向 Rust 把语法当代码精雕（单科 95），tpc 走向 TOML 把语法当资产
  （全科 80）。tpc 与 pyverilog 的亲缘比 Veryl 更近——共享"语法是描述不是
  代码"的核心信念，只是载体从 PLY 文法变成 TOML + 引擎。两作者（dalance /
  Takamaeda-Yamazaki）同为日本人，日本学术/开源圈在 HDL 工具链的持续贡献
  是真实生态现象（客观陈述，非优劣判断）。**tpc 工具链定位面向整个语言
  生态（ROADMAP「工具链定位」），Verilog 是第一个应用实例而非领域绑定**——
  与 Veryl/pyverilog 的 HDL 亲缘是路线源头关系，不是身份绑定。

### cairn（Scala）— 增量解析

- 语言 = `Fragment` 片段组合（`provides/requires/excludes`）→ 内容寻址（每个语言/产物有 digest）
- **双向文法**：一个 `GrammarSpec` 同时生成 parse + print，`RoundTrip.check` 验证 parse∘print 定律，`Concrete.put` 做格式保留编辑（字节级 splice）
- **借鉴点**：`Grammar.scala` 的增量失效（`invalidateFrom` token 缓存）——TODO P3 增量解析的参考实现

### lvca（OCaml）— provenance

- 抽象语法用 `valence`（绑定数量/种类）描述，ppx 从字符串生成 OCaml 类型
- **借鉴点**：`Provenance.t`（每个节点带 range）是一等公民——TODO P3 前置（Node 缺 token span）

### rascal（Java）— 元编程语言

- 完整元编程语言（type checker + interpreter + compiler + REPL），`grammar(...)` 定义文法，GLR 广义解析器
- **借鉴点**：具体语法模式匹配（元语言里写对象语言模式）——transform 插件若用 TOML 声明模式匹配 AST，可降低配置门槛（大 feature，v0.2 再议）

### Koine（Python）— 配置驱动 parser/transpiler（2025-09 深调研）

- 语法即数据：YAML/JSON/TOML 定义 lexer + 文法 + AST 形状 + transpile 模板，引擎消费 dict
- **项目印象**：单作者（Chris Bates）的完整作品——870 行 README + 34KB PARSING.md + 18KB TRANSPILING.md 的文档体系，README 主动声明适用/不适用场景（快速 DSL 原型 vs 高性能/复杂语义/IDE 级错误恢复），边界诚实；91 tests 全绿；定位清晰："built for designers—not compiler engineers"，为 agent scripting / 游戏 modding / 运行时改文法而生
- **与 tpc 的差异**（各有取舍，非优劣）：

| 维度 | Koine | tpc |
|------|-------|-----|
| 解析引擎 | 基于 parsimonious（PEG 库）构建 | 自研递归下降+回溯+Pratt，零外部依赖 |
| 管线 | lexer → parser → AST → transpiler（4 段，聚焦 DSL 快速成型） | 8 段：preprocessor → lexer → parser → linter → analyzer → transform → renderer |
| 语义分析 | 明确不做（README 声明由宿主语言 visitor 承担） | analyzer：作用域/符号/类型 |
| 静态检查 | 无 lint 概念 | 反向解析器 linter（token 级） |
| 格式化 | 无（transpiler 生成新代码） | renderer：Doc IR 格式化 |
| 错误处理 | 报第一个语法错误即停（README 声明） | 解析诊断 + lint 诊断 |
| 验证 | 91 tests | 771 pytest + e2e 93 + recall 31/31 + diff 124 vs Verible + fuzz ~8000 |
| 语言资产 | 教学级示例（calculator、py/js 子集、slip） | 完整 Verilog 包（57 TOML）+ c4 示例语言 |
| 维护状态 | 0.10.3，2025-07 起约 1.5 个月开发，2025-09-08 后暂无活动 | v0.1.0，今日上线，CI 12 任务矩阵全绿 |

- **值得参考的部分**：
  - 🔥 subgrammar 跨文件多模块语法组织 + placeholder 隔离开发（语法级细粒度组合——tpc 现有目录级多语言包，细粒度跨文件组合可参考）
  - 💡 stateful lexer 的 INDENT/DEDENT 缩进 token 方案（tpc 目前语言无需缩进语法，未来语法包可参考）
  - 💡 transpiler 的 `state_set` 状态化模板输出（tpc transform 是配置驱动，状态化输出思路可借鉴）
  - 💡 文档先行 + 边界自明的写法（README 明确写"不适合什么"，值得学习）
  - 📌 技术路线差异观察：基于现成 PEG 库可快速成型，自研引擎控制力更强但投入更大——两种路线各有适用场景，Koine 在它的目标场景（快速 DSL 原型）下路线是自洽的

### ohm-js（JavaScript）— 声明式语法 + 语义惰性求值（2026-08-31 深调研，agent-reach + 源码镜像）

- 定位：基于 PEG 的解析工具箱（5.5k stars，MIT）。核心主张 = **语法与语义完全分离**：
  grammar 只做识别（纯声明），semantic actions 独立定义（操作/属性），
  语义**惰性求值**（只有结果被需要才执行，失败分支/未提及子表达式不跑）。
  monorepo（compiler/runtime/semantics/cli 分包），ohm 语法**自举**
  （`ohm-grammar.ohm` 描述自己）。
- **与 tpc 的差异**（各有取舍，非优劣）：

| 维度 | ohm-js | tpc |
|------|--------|-----|
| 语法形态 | **单文件 DSL**（`Arithmetic { Expr = "1 + 1" }`，PEG 变体，大小写区分 syntactic/lexical 规则，隐式空白跳过） | **多文件 TOML**（结构协议：production/node 绑定/布局/符号，无隐式空白——token 显式） |
| 语义附着 | **独立 Semantics 对象**（wrapper 装饰 CST，操作/属性按规则名分发，惰性 + 记忆化） | **node 字段绑定**（`cond = "$3"` 语法 TOML 显式命名子节点）+ analyzer 符号表 + postpass 插件 |
| CST 节点 | **通用极简树**（只有 matchLength + children，无语言特定字段；访问靠 `childAt(i)` 位置） | **字段丰富**（语法绑定命名子节点，renderer/analyzer 直接按名取） |
| 语法扩展 | **OOP 继承**（grammar 继承 supergrammar，规则 override，extend = `新体 \| 旧体`） | **inject 声明式**（`[inject] targets` 挂载，requires 依赖链） |
| 左递归 | ✅ 支持（PEG 变体，左结合运算符自然写） | 无（递归下降 + Pratt 处理运算符优先级） |
| 增量解析 | ✅ **内置**（`replaceInputRange` 维护 packrat memo 表，编辑→局部失效） | 无（P3 增量解析是 v0.2 roadmap，未实现） |
| 错误恢复 | 报错但**不可恢复继续**（PEG 特性） | linter 前置（token 级坏输入诊断）+ parser 截断即失败 |
| 位置模型 | **Interval**（源码区间，CST 节点自带 matchLength → 区间可算） | `_pos_line/_pos_col`（parser 挂载）+ token span（P3.1 未做） |
| 语义执行 | 惰性（操作只在需要时跑，访问者式前后控制） | 遍历期符号收集 + postpass 链式走查（主动全跑） |

- **亮点单独说明**：
  - 🔥 **语义惰性求值**：操作/属性只在结果被需要时执行——回溯分支的语义
    不跑、未提及子表达式不跑。tpc 的 postpass 是全量主动跑（每文件全树
    遍历），ohm 的"按需语义"对性能是天然优势（也是 CodeQL path-problem
    的声明式 cousin）
  - 🔥 **增量解析 = packrat memo 表维护**：`replaceInputRange` 只失效
    受影响区间（`clearObsoleteEntries(pos, startIdx)`）——这正是 tpc
    P3.2/P3.4 增量 check 缺失的**引擎级机制**（tpc 目前是"全量重解析"，
    P3 只规划了 span 绑定 + 失效传播，未定 memo 表方案；ohm 给了现成
    参照）
  - 💡 **属性级记忆化失效**（`_forgetMemoizedResultFor`）：语义操作结果
    缓存可按属性逐条失效——tpc 增量语义（P3.4）可借鉴"按规则/属性
    失效"而非全量重跑
  - 💡 **CST 通用树 + wrapper 分层**：节点零语义字段、语义全在 wrapper
    ——与 tpc"node 绑定字段"相反但各有取舍：ohm 换通用性（同一 CST
    多语义复用），tpc 换直接性（renderer/analyzer 免包装）
  - 📌 **左递归 PEG 支持**：tpc 用 Pratt 处理优先级（`05_expressions.toml`
    运算符表），ohm 用左递归规则——两种方案都能表达左结合，tpc 的
    Pratt 与"运算符=配置数据"哲学更贴合
- **可实现性评估**：
  - 🔥 **可做（低成本）**：P3.4 增量 check 的"按属性/规则失效"语义——
    ohm `_forgetMemoizedResultFor` 思路，tpc 规则声明失效键时参考
  - 💡 **可做（中成本）**：P3.2 增量重解析的 memo 表方案——ohm
    `replaceInputRange` 的区间失效是现成参照（tpc 需先 P3.1 span 绑定）
  - 📌 **路线观察**：ohm 证明"声明式语法 + 惰性语义"在 JS 生态可规模化
    （5.5k stars，编辑器/解释器/编译器多场景）；tpc 的 TOML 多文件
    结构协议在"语言知识不进代码"上走得更彻底（ohm 语义仍是 JS 代码），
    ohm 的语法 DSL 单文件形态对"语法即数据"是另一种取舍
  - ❌ **不借鉴**：PEG 变体语法形态本身（tpc 的 production 声明式已覆盖
    同等表达力且与渲染/符号体系集成）；惰性语义执行器（tpc 的 postpass
    主动模型与"语言知识不进代码"更匹配，惰性需 JS 闭包式语义对象，与
    TOML 规则模型不兼容）
- 来源：GitHub [ohmjs/ohm](https://github.com/ohmjs/ohm)（5.5k★，MIT），
  源码镜像 `E:\research\ohm-src\ohm-main`（doc/philosophy.md、
  doc/syntax-reference.md、packages/ohm-js/src/Matcher.js、Semantics.js、
  nodes.js）

### lyra（C++）— SystemVerilog 仿真工具链（2026-08 深调研，与 tpc 同期活跃的同龄人）

- 定位：现代 SystemVerilog 编译器 + 模拟器，多级 IR 管线，优先"编译+运行+调试"的迭代速度而非峰值仿真速度
- **项目印象**：作者 Shou-Li Hsu 的大工程——1238 commits（2025-04 起步，2026-01 起月均上百）、306 个源文件（include+src 约 1.2MB）、927 个 .sv 测试 case、12 个 CI workflow（Bazel build/test、clang-tidy、cpp-style、ascii 政策、架构检查、异常政策、nightly benchmark）全绿；commit 编号到 #1101；文档体系完整（HIR/MIR/LIR 分层契约、queue 化 TODO 管理）；MIT；5★/1 fork，无社区但工程投入极大
- **历史节奏**：与 tpc 相似——2025-04~06 起步后断档约 6 个月（2025-07~12），2026-01 以 423 commits 重新爆发并持续至今；仓库内 `archived/` 目录表明早期实现被整体归档废弃后重来（愿意推倒重做的信号）
- **与 tpc 的差异**（各有取舍，非优劣）：

| 维度 | lyra | tpc |
|------|------|-----|
| 领域 | SystemVerilog 全量编译器+模拟器（单语言深耕） | 通用配置驱动管线 + Verilog/c4 语言包（引擎通用） |
| 解析 | 复用 slang 的 AST（不自己写 parser） | 自研递归下降+回溯+Pratt（语法即 TOML 数据） |
| 语言/依赖 | C++23 + Bazel + slang + coroutine runtime | Python 3.11+ 零外部依赖 |
| 管线 | slang AST → HIR → MIR → LIR → backend::cpp | preprocessor → lexer → parser → linter → analyzer → transform → renderer |
| 侧重 | 语义执行（DPI-C、队列、联合、时序、$readmem） | 语法配置化 + 格式化（Doc IR）+ lint |
| 验证 | 927 个 case（.sv + case.yaml 期望） | 771 pytest + e2e 93 + recall 31/31 + diff 124 vs Verible + fuzz ~8000 |

- **值得参考的部分**：
  - 🔥 测试即文档的 case 组织：每个 case 一个 .sv + case.yaml（输入+期望声明），覆盖到语义细节（packed 布局、X/Z 传播、DPI-C ABI）——tpc 的差分/fuzz 门禁已覆盖正确性，此模式可补充"语义单例文档化"
  - 💡 政策即 CI：tools/policy/ 把 ascii 规范、异常规范、架构检查做成自动门禁（tpc 有硬约束 AGENTS.md + lint recall 门禁，可借鉴"把约定变成检查器"的做法）
  - 💡 分层 IR 契约文档（HIR/MIR/LIR 各层 contract）——tpc 各阶段接口已有 MODEL_INDEX 对应，可对照其"层间契约先行"的写法
  - 📌 复用成熟 parser（slang）聚焦语义层 vs 自研 parser 聚焦配置化的路线对照——lyra 验证了"语言工具链可以站在别人 parser 肩上"，tpc 验证了"语法作为可配置资产"的独立价值，两者不冲突
  - 📌 断档-回归 + 推倒重来的历史与 tpc 同构：2025 起步→断档→2026 重新爆发；lyra 用 `archived/` 明确废弃早期实现，tpc 用 TODO/milestone 保留演进脉络——两种"承认过去"的方式都诚实

### VAST（C++/MLIR）— 程序分析向塔式 IR 管线（2026-08 深调研）

- 定位：Trail of Bits 出品（DARPA 资助研究），C/C++ 程序分析与插桩的 MLIR 基础设施——"a tower of IRs as MLIR dialects"，为分析场景提供不同抽象层级的 IR 选择。444★/34 forks，Apache-2.0，CI（build/linter）全绿，2026-04 仍在推

**管线结构对比（逐阶段）：**

| 阶段 | VAST | tpc | 差异点 |
|------|------|-----|--------|
| 词法/语法 | 复用 Clang 的 AST（不自己写 lexer/parser） | 自研 lexer（token 定义驱动）+ parser（递归下降+回溯+Pratt） | VAST 站在 Clang 肩上；tpc 语法即数据 |
| 前端转换 | Frontend/Action.cpp：Clang AST → 首个 MLIR 方言（逐节点转写） | parser 直接产出 AST（`[Rule.parser.node]` 形状声明） | VAST 有显式转写层；tpc AST 形状在 TOML 里声明 |
| IR 组织 | **方言塔**：8 个方言（HighLevel/LowLevel/Core/Meta/ABI/Builtin/Parser/Unsupported），同源多级、逐级下降 | 单 AST + Doc IR（Wadler-Lindig 渲染） | VAST 每级 IR 独立可分析；tpc 一树贯穿 |
| 转换机制 | pass 管线 + **每 pass 后克隆模块**存入 module_storage，记录转换步骤链 + 位置反向链接（backlink） | transform 配置驱动 + 插件原语（primitives） | VAST 重但可完全回溯；tpc 轻但转换来源不可追溯 |
| 转换方向 | Conversion/：FromHL / ToLLVM / ToMem / Parser / ABI（方言间下降/上升） | transform：语义映射 + 配置驱动变换（typed_ports 展开、c4 降级） | 两者都有多向转换；VAST 靠方言对，tpc 靠插件 |
| 代码生成 | CodeGen + Target + ABI（生成 LLVM IR / 目标相关代码） | renderer：Doc IR → 格式化文本 | VAST 生成代码；tpc 生成格式化文本（不同目标） |
| 位置追踪 | 一等公民：每个 operation 的 loc 编码 backlink（源→IR 全程可回溯） | 解析诊断有 span；Node 缺 token span（TODO P3 前置） | **最大差距**：VAST 位置即架构；tpc 尚未绑定 |

**亮点（单独说明）：**
- **Tower 机制**：`lib/vast/Tower/Tower.cpp`——每个 pass 运行后克隆模块、把 pass 路径压入栈、更新 operation 位置使其编码"转换步骤链"。从任意 IR 节点可回答"这个节点从源文本怎么变来的"。这不是某个分析功能，是**架构级 provenance**：任何 pass 自动获得可追溯性，无需各 pass 自己维护
- 方言塔按抽象层级命名（High→Low→Core→Meta），分析者可取所需层级——分析器不用被迫消化完整 Clang AST

**可实现性评估（tpc 能否做）：**
- 🔥 **价值定位修正：这套思路给"变换器插件的作者"效果更好**。Tower 的"每步记录来源"对 tpc 引擎本身不是必需（tpc 目标是格式化/lint，不需要全链回溯），但对**写 transform 插件的人**是刚需：插件作者改语言行为时，最痛的是"我的原语对节点做了什么、为什么结果不对"。给 transform 插件层加"步骤日志"（每原语记录输入/输出节点对 + 来源）≈ VAST 的轻量版，且只服务插件作者，不拖累主路径
- 方言塔多级 IR：**不实现**（目标不同；"按需取层"已由切片覆盖）
- 克隆模块：**不实现**（无内存化 IR 持久需求）

### Foundry（Rust）— Ethereum 开发工具链（2026-08 深调研）

- 定位：blazing fast、portable、modular 的 Ethereum 应用开发工具链（Rust）；forge（构建/测试/fuzz/调试/部署）、cast（链交互）、anvil（本地节点）、chisel（Solidity REPL）。10570★/2607 forks，今日仍在推，Apache-2.0

**管线结构对比（逐组件）：**

| 组件 | Foundry | tpc 对应 | 差异点 |
|------|---------|----------|--------|
| 编译 | forge：Solidity → solc → ABI/bytecode（封装编译器，非自研） | parser+transform：TOML 文法 → AST → 展开 | Foundry 站在 solc 肩上；tpc 引擎自研 |
| 测试 | forge test：内置测试框架 + **属性 fuzz**（invariant 测试） | e2e 93 + 差分 124 + fuzz ~8000（独立 harness） | 两者都有 fuzz；Foundry 把它做成产品功能 |
| 执行 | anvil：本地 EVM 节点（fork 主网、状态快照） | 无（tpc 明确不做仿真/执行） | 领域不同：Foundry 有运行时，tpc 无 |
| 链交互 | cast：RPC 瑞士军刀（查询/发交易/解码） | 无对应 | 领域不同 |
| REPL | chisel：Solidity 交互式 REPL | 无对应 | 领域不同 |
| 共享核心 | crates/ 多 crate：anvil 拆 core/rpc/server，公共库复用 | 单包 + grammar/<lang> 语言包 | **同构**：组件独立、核心共享 |

**亮点（单独说明）：**
- **模块化切片实证**：forge/cast/anvil/chisel 是四个独立可安装的组件（`foundryup` 管理），共享底层 crate——**"工具链按能力切分"在 10k★ 项目里被验证成立**，且每个切片单独可用、无需理解全栈
- **碎片化 changelog**：`.changelog/` 目录**每个 PR 一个 md 碎片**，release 时聚合发布说明——解决"手写 changelog 漏记/拖延/合并冲突"，且 changelog 随 PR 评审（reviewer 能看到本次改动说明）
- benchmark 公开页（getfoundry.sh/benchmarks）：把性能数据当作品资产展示

**可实现性评估（tpc 能否做）：**
- 🔥 模块化切片：**已实现**（tpc-fmt/tpc-lint/tpc 三 exe + 切片声明），Foundry 只是外部验证了该方向
- 📌 **价值定位修正：目的上无重合，仅工具组织方式相似**。Foundry 是 EVM 应用开发工具链（编译+测试+链交互+节点），tpc 是配置驱动语言工具链——业务目的不同，可借鉴的只有"组件独立、核心共享"的组织方式（已实现）与碎片化 changelog（低成本可选）。fuzz/测试/执行等能力是各自领域的平行实现，无移植价值
- 🔥 碎片化 changelog：**高可实现，低成本**。tpc 可加 `docs/changelog-fragments/<PR>.md` + 发布时聚合脚本（Python 十几行）；或不引入，维持当前手动小节（发布不频繁时手动够用）
- 💡 foundryup 工具链管理器：**中可实现**。tpc 若做多版本分发（当前 exe 单版本）才值得；零依赖下用脚本实现即可
- 💡 benchmark 公开页：**高可实现**。tpc 已有 fuzz/edge 数据，发布一个静态 benchmark 页即可

### vbcc（C）— 1989 年起的可移植 C 编译器（2026-08 深调研）

- 定位：Volker Barthelmann 与 Frank Wille 的可移植 C 编译器（1989 年起，至今维护）；一个编译器支撑 13 个目标后端（6502/832/alpha/bi386/c16x/hc12/i386/m68k/m68ks/ppc/qnice/vidcore/z）。GitHub 镜像（Leffmann/vbcc）25★/12 forks（2016-2023 快照），原作持续维护

**管线结构对比（逐阶段）：**

| 阶段 | vbcc | tpc | 差异点 |
|------|------|-----|--------|
| 预处理 | 自带 ucpp + vbcc_cpp（集成预处理器） | preprocessor（宏展开/条件编译/反向映射） | 两者都内建；tpc 有反向桥（锚点回插） |
| 词法/语法 | 手写递归下降 + 语法表（parse_expr.c/statements.c/declaration.c/type_expr.c） | 自研 lexer + 递归下降+回溯+Pratt（语法在 TOML） | 同代设计；tpc 语法外置为数据 |
| 中间代码 | **IC 三地址码**（ic.c/icn.c：op1/op2/op3 三操作数，流向图 flow.c） | AST + Doc IR（无显式中间码） | vbcc 有经典三地址 IC；tpc 一树贯穿 |
| 优化 | **手写 pass 序列**：alias.c（别名）/cse.c（公共子表达式）/loop.c（循环）/range.c（区间分析）/regs.c（寄存器分配 65KB）/opt.c（主循环，pass 编号重复至收敛） | 配置驱动变换（无传统优化器） | **最大差异**：vbcc 是经典优化器，tpc 不做深度优化 |
| 后端 | machines/ 目录：**一个后端一个目录**（含 make.rules + 每后端 texinfo 文档），13 个后端共享前端+优化器 | grammar/<lang>/ 一个语言一个目录（TOML + 插件） | **同构**：都是"多目标=多目录"极简抽象 |
| 配套工具 | vcpr（剖析）/vprof（性能）/vsc（源码检查）/ucpp | linter（反向解析器）+ analyzer（语义检查） | 都自带配套工具链；vbcc 按独立组件，tpc 内建管线 |

**亮点（单独说明）：**
- **machines/ 目录抽象**：13 个后端，每个就是一个目录 + 通用接口 + 一册文档——证明"多目标=多目录"的极简抽象足以支撑 13 个不同 ISA（6502 到 PowerPC）
- **30 年单作者长跑**：可移植性（13 后端）本身就是项目生命力的来源——换目标不换引擎，让编译器活过 3 个十年
- **单文件大 pass 的克制**：regs.c 65KB、opt.c 65KB——不搞过度分层，pass 就是文件
- **歧义处理**：C 的经典"声明 vs 表达式"歧义（`a * b;` 是乘法还是指针声明）靠 `declaration(int offset)` 探测函数消解——token 流里向前探一个：命中类型关键字白名单（int/char/struct/...）或**符号表回查 `storage_class==TYPEDEF`**（lexer-hack 式）即判定为声明；探测前后用 `push_token`/`next_token` 保存恢复 token 流，探测完指针复位

**可实现性评估（tpc 能否做）：**
- 🔥 machines/ 目录抽象：**已同构**。tpc 的 grammar/<lang> 就是同款模式（verilog/ + c4/ 两语言包已验证）；可扩展时照抄"每语言一目录 + 独立文档"的组织
- 💡 **歧义处理启发（管线目的虽异，此处有借鉴价值）**：tpc 已有 A/B 类消歧（Level 1 变长前瞻 + Level 2 试解析）+ end_case 语句边界推导。vbcc 的"向前探一个 token + 符号表回查"提示一种**低成本消歧路径**：当 grammar 里出现"同一 token 起始的声明/表达式二义"时，可声明一个"探测规则"（token 白名单 + 语义回查），比 Level 2 试解析更轻。Verilog 的 `parameter x = 1;` vs `x = 1;` 类场景可评估（当前靠语句发现器区分，未用探测式）
- 💡 手写优化 pass：**不实现**。tpc 定位是配置驱动浅层语义（格式化/lint/展开），深度优化（别名/寄存器分配）超出设计目标，README 已声明边界
- 💡 配套工具独立组件化（vcpr/vprof/vsc 各自独立）：**中可实现**。tpc 的 linter/analyzer 已内建管线，若要做"切片更细"可参考 vbcc 把工具拆成独立命令（tpc-fmt/tpc-lint 已部分实现）

### sv2v（Haskell）— SystemVerilog→Verilog 转换器（2026-08 深调研）

- 定位：zachjs 出品的 SystemVerilog 到 Verilog 源到源转换器（748★，BSD-3-Clause，2019 起，2026-08 仍在推）——把 SV 新特性（interface/struct/enum/typedef/foreach/logic...）降级为可综合 Verilog-2001，供老工具链使用
- **收录观察**：作为标准 source-to-source transpiler（SV→V），却未被 [awesome-transpilers](https://github.com/transpiler/awesome-transpiler) 收录（该列表无任何 SystemVerilog 条目）——收录维护者视野盲区，非项目问题；反过来提醒 tpc 的 references.md 收录也要有系统索引，避免同样漏项

**管线结构对比（逐阶段）：**

| 阶段 | sv2v | tpc | 差异点 |
|------|------|-----|--------|
| 词法 | 手写 lexer（Lex.x，alex 生成） | 自研 lexer（token 定义驱动） | 同代设计；tpc token 在 TOML |
| 语法 | 手写 yacc grammar（Parse.y，happy 生成）+ Preprocess | 自研递归下降+回溯+Pratt（语法在 TOML） | sv2v 是 LALR 生成式；tpc 是手写式配置驱动 |
| AST | Language/SystemVerilog/AST：Expr/Stmt/Type/Decl/ModuleItem 分层定义 | `[Rule.parser.node]` 形状声明 | sv2v AST 是显式 Haskell 类型；tpc AST 形状在 TOML |
| 转换 | **src/Convert/ 约 50 个 pass，每个文件一个 SV 特性**（Interface/Struct/Typedef/Foreach/Scoper/ResolveBindings/ImplicitNet/Enum...） | transform 插件原语（primitives） | **同构**：都是"一特性一转换单元"；sv2v 是 Haskell 函数链，tpc 是 TOML+插件 |
| 语义 | Scoper/ResolveBindings（名字解析、隐式网表推导） | analyzer（作用域/符号/类型） | 都有语义层；sv2v 深度绑定 SV 语义 |
| 输出 | 降级为 Verilog-2001 文本 | renderer：Doc IR → 格式化文本 | 都产出 Verilog 文本；tpc 还保格式/保注释 |
| 验证 | **1046 个测试文件**：test/core 每个 .sv 配 .v 期望 + .sv.pat 模式 + test/error 大批错误用例 + test/lex 词法 + test/relong 长回归 + 仿真对照（tb） | 771 pytest + e2e 93 + recall 31/31 + diff 124 vs Verible + fuzz ~8000 | 两者都是"用例即文档"；sv2v 用真实仿真做最终校验，tpc 用 Verible 差分 |

**亮点（单独说明）：**
- **一特性一 pass 的组织**：src/Convert/ 下 Interface.hs、Struct.hs、Typedef.hs、Foreach.hs……约 50 个转换，每个文件专注一个 SV 特性的降级——新特性接入 = 新文件 + 挂进链，可独立测试
- **测试即文档 + 仿真终验**：1046 个用例，每个 .sv 带期望 .v（有的还带 .pat 模式匹配、tb 仿真文件）——不只语法正确，还过仿真验证行为等价
- **bugpoint 工具**：内置最小化复现工具（test/bugpoint/），出问题时自动缩减到最小用例——调试基础设施完备

**可实现性评估（tpc 能否做）：**
- 🔥 **一特性一 pass：已同构**。tpc 的 transform 插件原语（typed_ports、semantic_check 都是独立原语）就是同款组织；sv2v 验证了"每特性独立转换单元"在 50 个特性规模下依然清晰
- 💡 **SV 兼容路线参考**：tpc 的 Verilog 包声明"无 SystemVerilog"（README 边界），若未来要接 SV 特性（interface/struct/enum），sv2v 的降级方案（SV→V-2001）是现成路线图——每特性一个插件原语，逐个接入
- 💡 **仿真终验**：tpc 用 Verible 差分验证格式正确性；sv2v 用真实仿真（iverilog + tb）验证行为等价——tpc 不做仿真（README 已声明），但差分门禁已覆盖其定位内的验证需求
- 💡 **bugpoint 最小化工具**：tpc 的 fuzz 已能生成复现用例，若补"自动缩减到最小用例"可参考 sv2v 的 bugpoint（低成本小工具）

### verible-verilog-format（Google）— Verilog 格式化高精度标杆（2026-08 深调研）

- 定位：chipsalliance/verible 的 SystemVerilog 官方 formatter（C++，与 slang/tree-sitter-verilog 并列的活跃解析生态）；tpc 差分测试已带其 exe（tests/differential/.tools/verible/）做格式对照
- **方法**：token 流 → 语法结构划分（语句/声明/端口组）→ **布局决策**（每 token 间选择换行/空格/对齐，受缩进策略与最大列宽约束）→ 输出；注释挂 token 流随行保留，空行保留可选
- **亮点（单独说明）**：
  - **token 级保真**：注释锚定在 token 间隙，换行/空行保留度可配——"保格式/保注释"是设计目标而非后处理
  - **列对齐是布局决策的一部分**（端口声明、实例化参数对齐），不是文本后处理——对齐进入决策模型
  - 决策目标明确：换行只在合法断点、缩进连续、对齐组稳定
- **可实现性评估（tpc 能否做）：**
  - 💡 **布局决策模型**：tpc 世界 A（Doc IR）缺"对齐"、世界 B（文本 pass）靠行号耦合——verible 的"token 流 + 决策"是第三种形态：结构在 token 间隙上做决策，天然保注释、可对齐。重设计候选之一
  - 💡 **差分基线复用**：tpc 已与 verible 差分 124 例，重设计后继续以它为 Verilog 高精度目标参照（recall/误报纪律同款）
- **P1.6 折行关闭结论（2026-08-27，分区策略各有取舍）**：verible"每种列表一个策略"
  （参数/端口/声明独立 wrap/stack 策略）vs tpc"统一惩罚表 + 排除清单"（逗号<逻辑<
  算术<三目 + 端口/声明/宏/注释不折）——实质需求（哪些折/哪些不折）已由排除清单
  覆盖，独立策略是形式差异，**各有取舍不追**（tpc 排除清单更简单，verible 独立策略
  更精细但复杂度高）。折行对比验证：picorv32 format 后 75→73→65→9 条超宽，9 条全为
  设计内不折类型（concat 无顶层安全断点/多声明对齐/宏 `debug`/块头 case 分支/双层
  括号首段无更早断点）——无"应折未折"的普通表达式，剩余是"无安全断点"的固有上限

### Verilog 静态检查工具群（2026-08 研判）— tpc-check 的"pylance 化"参照

> 研判动因：把 Verilog 静态检查工具纳入参照系，为 tpc 检查插件体系（linter + analyzer
> semantic_check/inst_check 插件）提供实现参照；目标场景 = **模型生成 v 文本 → tpc-check
> 当 pylance 用**（即时诊断、机器可读、可豁免）。以下五个工具覆盖了"诊断模型 / 规则组织 /
> 配置 / 输出 / suppress / 服务化"六个维度。

#### 各工具定位与存续

| 工具 | 定位 | 存续状态 |
|------|------|----------|
| [verible-verilog-lint](https://chipsalliance.github.io/verible/verilog_lint.html)（C++，CHIPS Alliance） | 官方 lint：语法/风格规则 + rule-sets 配置 | 活跃（与 formatter 同仓库持续发版；tpc 差分已带其 exe） |
| [Verilator `--lint-only`](https://github.com/verilator/verilator)（C++，Veripool） | 仿真器附带语义级 lint：W 码警告体系（WIDTH/LATCH/MULTIDRIVEN/UNOPTFLAT 等 200+ 条） | 极活跃（业界事实标准，持续发版） |
| [slang `--lint-only`](https://github.com/MikePopoloski/slang)（C++，微软资助） | 解析器生态 + lint：unused/suspicious 规则族；diagnostics severity 体系 | 活跃（SystemVerilog 解析核心） |
| [svlint](https://github.com/dalance/svlint)（Rust） | 纯规则化风格/错误 lint：100+ 规则，`.svlint.toml` 逐条 severity | 较活跃（0.3.x；低RISC-V ibex 等真实项目采用 `.svlint.toml`） |
| [hdl_checker](https://github.com/suoto/hdl_checker)（Python） | "Repurposing existing HDL tools"：封装 pyGHDL/verible/slang 等后端 → LSP 诊断服务 | 维护放缓但架构仍有效（编辑器集成参照） |

#### 诊断模型与配置对比（各有取舍，非优劣）

| 维度 | verible-lint | Verilator | slang | svlint | tpc-check 现状 |
|------|--------------|-----------|-------|--------|----------------|
| 规则 ID | 规则名（line-length/module-filename）+ 默认启停 | W 码（WIDTH/BLKSEQ…） | diagnostics code + severity | 规则名（explicit_case_default…） | linter 阶段性 code（phase-expr）+ 语义 WC001 等——缺稳定规则命名空间 |
| severity 配置 | rule-sets（`-rule-set=all/style` 叠加 ±规则） | `.vlt` 文件 + `--Wno-*` | `--diag-*` + waiver 文件 | `.svlint.toml` 逐条 error/warning/hint/info | 语义检查有 primitive 配置；linter 规则从语法推导，无显式规则表 |
| suppress | 部分规则可 `// verible-format` 类注释 | `/* verilator lint_off/on */` 注释对 + `.vlt` lint_off | WaiverManager（规则名+位置） | 规则级 disable | 无 |
| 输出格式 | 文本 + `--print_rule_descriptions` + JSON | 文本 | `--diag-format`（文本/JSON） | JSON/GCC/checkstyle 等 | 文本（CLI 打印） |
| 服务化 | 无（CLI） | 无 | 无 | 无 | 无（CLI）；hdl_checker 参照封装路线 |

#### 亮点（单独说明）

- **Verilator 的 suppress 注释对**：`/* verilator lint_off WIDTH */ … /* verilator lint_on WIDTH */` 是源码内豁免的事实标准形态——对被生成代码（模型输出）尤其关键：生成器知道自己哪里会"故意违规"（如非标缩进），可在生成时内联豁免，检查器按注释对跳过区间。
- **verible 的规则描述可输出**：`--print_rule_descriptions` 打印全部规则与默认启停——规则体系自身就是文档，IDE/脚本可消费。
- **svlint 的规则表 + 逐条 severity**：规则全是数据（Rust 规则结构体 + 文档），`.svlint.toml` 按项目覆盖——"规则即配置"与 tpc 配置驱动哲学同构。
- **hdl_checker 的后端封装**：不自己解析，把成熟工具的输出翻译成 LSP Diagnostic——"检查服务 = 适配器"形态，工具链迭代成本低。

#### 可实现性评估（tpc 能否做；映射到"模型生成 v → tpc-check 当 pylance"）

- 🔥 **稳定规则 ID + 机器可读输出（第一步，低成本）**：给 linter/语义检查诊断建立稳定规则命名空间（`T001` 语法结构 / `WC001` 语义 / `N001` 命名），`tpc check` 增加 `--format json`（纯 stdlib 手写即可）。这是"pylance 式"消费的前提——编辑器/模型/CI 都需要稳定 ID + 结构化输出，verible/slang/svlint 都有 JSON 输出实证。
- 🔥 **suppress 注释对（第一步，低成本）**：仿 Verilator `lint_off/lint_on`，tpc 实现 `/* tpc-check off <rule> */` 区间豁免（或 `// tpc-check: disable-line` 单行）。模型生成代码场景的刚需——生成器在"故意非标"处内联豁免，门禁不误伤。
- 💡 **规则表 + severity 配置（第二步）**：检查规则显式化为 TOML 数据（规则 ID → 描述 → 默认 severity → 适用阶段），用户配置覆盖 severity（对齐 svlint `.svlint.toml` / verible rule-sets）。tpc"语言知识进 TOML"哲学在检查侧的落地；P1.9 的 naming_check 是第一条显式规则（Sigasi 式 pattern 表）。
- 💡 **waiver 清单（第二步）**：项目级豁免文件（路径/规则/行号），slang WaiverManager 参照——第三方代码目录整体豁免，避免给每个文件加注释。
- 📌 **LSP 服务化（路线观察）**：hdl_checker 的"封装后端 → LSP Diagnostic"是 pylance 式体验的最终形态；tpc 零依赖下可 stdlib 手写 jsonrpc（几百行），但需真实需求驱动（编辑器接入）再立项。
- 📌 **语义级警告（WIDTH/LATCH/MULTIDRIVEN 类，不实现）**：Verilator 的宽度/锁存/多驱动检查依赖类型与宽度推断，超出 tpc"配置驱动浅层语义（格式化/lint/展开）"定位，README 已声明边界——作路线观察，若未来做类型推断（analyzer 扩展）再评估。
- ⚠️ **避坑**：svlint 自研 parser 的维护负担（规则演进受 parser 能力约束）——tpc 复用语法 TOML（规则=语法资产）无此问题，是"反向解析器"路线的优势；hdl_checker 后端版本耦合（verible 输出格式变化即坏）——tpc 若封装外部工具做差分基线即可，不做运行时依赖。

**落地路径小结**：第一步（规则 ID + JSON + suppress）≈ 一个 `tpc check --format json` + 注释豁免机制，纯增量、零外部依赖，即可支撑"模型生成 v → tpc-check 检查"的脚本化闭环；第二步（规则表配置化）与 P1.9 naming_check 合并推进。

#### 诊断链多维对标结论（2026-08-28 定稿，0.1.1 第二目标）

- **svlint 是对齐/参照工具，不是依赖**——主路径自研（诊断链三层面 + 跨文件易错点），svlint 提供规则工程化蓝图与规则清单，不引入运行时依赖（与 P2.6"封装外部工具做差分基线即可"判断一致）
- **"最好的对标"分维度**，无单一最佳：
  - 🔥 **规则工程化形态** → svlint：SyntaxRule 接口（节点监听 + 配置注入）、命名规则族 30 类按 kind 分发、suppress 注释对、插件——**自定义检查层/名称检查的组织形态蓝本**
  - 🔥 **语义级易错点** → Verilator `--lint-only`：W 码 200+（WIDTH/LATCH/MULTIDRIVEN/UNOPTFLAT）——**语义层 pass 的易错点清单与判定方向**（svlint 无语义层，这块给不了）
  - 💡 **规则集稳定/文档** → verible-verilog-lint：rule-sets 配置 + `--print_rule_descriptions` + 稳定规则名——**规则 ID 命名空间与文档形态参照**
- **映射到诊断链三层面**：语法层 = 现 linter（自研，无对标）；语义层 = semantic_check 插槽 + Verilator W 码清单参照；自定义层 = capabilities + 名称检查示例（svlint naming 族蓝本）
- **落地节奏**：结论先行，实现逐步推进（名称检查示例 → 规则表 schema → 语义易错点规则）；svlint/verible 规则清单按需移植，Verilator 语义检查作路线观察（类型推断超当前定位，README 边界已声明）

### svlint（Rust）— 规则工程化闭环范本（2026-08 深调研，dalance 作品链第二站，agent-reach + 源码镜像）

- 本地源码镜像：`E:\research\svlint`（浅 clone，v0.9.5）；调研日期 2026-08-26
- 定位：dalance（Veryl 作者）的 SystemVerilog linter（IEEE1800-2017 Annex A 合规），Rust，
  **基于 sv-parser**（作者自己的 parser crate）——linter 不自己写 parser，站在生态 parser 肩上
  （与 verible-verilog-lint 复用同一 verible parser、slang lint 复用 slang parser 同模式）；
  390★/45 forks，MIT，2019-10 创建，v0.9.5（2025-11）后仍活跃；经 svls 集成编辑器
- 管线结构：`CLI（clap）→ 配置搜索（SVLINT_CONFIG 环境变量 / 当前目录向上 ancestors 找
  .svlint.toml）→ textrules 按行检查 → sv-parser 预处理+解析 → syntaxrules 遍历 CST 节点
  事件流（Enter/Leave）→ Printer 输出`；两阶段规则：TextRule（StartOfFile/Line 事件）与
  SyntaxRule（AST 事件监听，每条规则自己决定关心哪些 RefNode 类型）
- **规则工程化闭环（最大亮点，build.rs + mdgen 双生成器）**：
  - 🔥 **build.rs 目录扫描即登记**：正则提取 `syntaxrules/`/`textrules/` 每文件首个
    `pub struct` → 生成 4 份代码：模块声明+re-export、配置结构体（逐规则 bool 字段 +
    `#[serde(deny_unknown_fields)]`）、`enable_all()/gen_*()` 实现、**测试代码**
    （testcases/{pass,fail}/{rule}.sv 按 80 个 `/` 分隔符切子用例 → 每子用例一个 `#[test]`）——
    **新增规则 = 放一个文件，登记/配置/测试全自动**，无手工接线
  - 🔥 **mdgen 文档/规则集生成**：`md/ruleset-*.md`（含 ```toml/```sh/```winbatch 代码块）→
    生成 `rulesets/*.toml` + `svlint-*`（POSIX wrapper）+ `svlint-*.cmd`（batch wrapper）+
    `svls-*`（LSP wrapper）——**规则集即独立命令**；规则 + testcases + md/explanation 拼出
    MANUAL.md（13339 行，每规则 Hint/Reason/Pass&Fail Example/Explanation + See also）
  - 🔥 **规则命名即分类**（mdgen `partition_syntaxrules`）：`style_`/`tab_` 前缀 → style 类，
    `prefix_`/`lowercamelcase_`/`uppercamelcase_`/`re_`/`_with_label` → naming 类，其余
    functional——类别信息编码在规则名里，文档自动分区
  - 🔥 **RENAMED_SYNTAXRULES 迁移表**：旧规则名 `check_rename` 警告 + `--config-update`
    `migrate()` 就地改写配置；旧名未迁移导致退出码 1——**强制用户升级配置**，不静默兼容
  - 🔥 **注释控制 suppress**：`/* svlint off rulename */` / `/* svlint on rulename */` 注释对，
    `update_ctl_enabled` 在 Enter Comment 节点时正则更新启停表——**与 Verilator lint_off/lint_on
    同款机制**（references.md 已研判，svlint 是第二个实证）；明确"textrules 不可注释控制"
    （文本规则不解析注释，设计取舍合理）；pass 测试用例直接演示豁免
  - 🔥 **插件机制**：`-p libfoo.so` 用 `libloading` 加载动态库，导出 `get_plugin() -> Vec<Rule>`
    （extern "C"），`pluginrules!` 宏收集规则——**外部规则运行时动态加载**，与 tpc
    capabilities 协议同类设计（svlint 载体是编译语言动态库，tpc 是 Python 模块）
  - 💡 **规则参数化**：命名规则的正则（`re_required_*`/`re_forbidden_*`，默认
    `^[a-z]+[a-z0-9_]*$` 等）、端口前缀（`i_`/`o_`/`u_`/`mod_`/`pkg_`/`ifc_`）、textwidth/
    indent/copyright 全是 `[option]` 配置项——规则行为由配置注入，规则代码只写判定
  - 💡 **规则 trait 四件套**：`check/name/hint/reason`——诊断 ID、提示、理由分离，
    MANUAL 与 `--config-example` 全靠它生成（verible `--print_rule_descriptions` 同款思路）
  - 💡 **精确定位**：`FailAt(offset,len)` / `FailLocate(Locate)`，诊断精确到节点内子位置；
    共享工具 `check_regex`/`check_prefix` 被命名/前缀规则族复用
  - 💡 **输出三模式**：rustc 风格 pretty（`-->` 定位 + `^` 标注 + hint/reason 两行）/
    `--oneline` 单行 / `--github-actions` workflow command（`::error file=,line=,col=::hint`）——
    机器可读输出是内置的，不做第二套序列化
  - 💡 **编码检测**：chardetng 猜编码（GBK 中文注释也能处理，有专门测试）——SV 生态现实
  - 📌 **parser 复用**：sv-parser crate 提供 CST + NodeEvent 遍历——省下 parser 投入，但
    规则演进受 parser 能力约束（references.md 避坑已记，tpc 反解析器路线无此问题）

- **诊断链插件深度调研（2026-08-28 补，源码镜像 E:\research\svlint 直读）**——0.1.1
  第二目标（诊断链插件：语法层 linter / 语义层 pass / 自定义检查层 + 跨文件易错点 +
  名称检查示例）的规则架构参照：
  - 🔥 **规则接口 = 节点事件监听 + 配置注入**：`SyntaxRule::check(&mut self, syntax_tree,
    event: &NodeEvent, config: &ConfigOption) -> SyntaxRuleResult`（Pass/FailAt/FailLocate）
    ——每条规则在 Enter 事件按 RefNode 类型匹配（如 `ModuleAnsiHeader`），`unwrap_node!`
    取子节点、共享工具（check_prefix/check_regex）判定。**与 tpc semantic_check 插槽
    （post-pass 钩子）架构同构**——svlint 是"事件监听 + 配置注入"规则形态规模化
    （~190 条）的实证
  - 🔥 **配置扁平注入（ConfigOption serde 结构）**：~80 个规则选项字段（prefix_*×7 +
    re_required_*×30 + re_forbidden_*×30 + 其他）是**单一扁平结构**，serde 反序列化 +
    `deny_unknown_fields` + 默认值函数——**规则代码只写判定，规则行为全由配置注入**
    （规则读 `option.prefix_module` 等）。tpc 的 [[checks]] schema / pattern 表可直接
    参照此形态（配置与规则代码分离）
  - 🔥 **命名规则族 = 按 kind 分发的完整实证**：prefix_module/prefix_input/... +
    lowercamelcase_module/... + re_required_*（module/function/task/genvar/instance/
    port_input/port_output/... 30 类）——**正是 P1.9 名称检查的蓝本**：kind → 正则/
    前缀配置（默认值如 `^[a-z]+[a-z0-9_]*$`），规则代码 = kind 匹配 + 判定
  - 📌 **跨文件现状**：`-f/--filelist`（sv_filelist_parser：files/incdirs/defines +
    `--dump-filelist`）——**跨文件 = 批处理 + filelist 宏/incdir 展开，规则是单文件
    per-run，无跨文件符号表**。tpc 语义层（作用域链 + inst_check 已跨文件）的
    "跨文件易错点"是**差异化能力**（svlint 无）
  - 💡 **规则 trait 四件套实证**：check/name/hint/reason——hint 接收 config（提示随
    配置动态生成，如"Prefix `module` identifier with \"i_\""），MANUAL 自动拼
  - 💡 **插件形态对照**：pluginrules! 宏 + Rule enum（Text/Syntax 指针）+ get_plugin()
    extern "C" 动态库——tpc capabilities（Python 模块）同类设计，Python 载体零编译
    更轻；**自定义检查层（用户自由度）tpc 已有协议基础，缺的是"注册 + 文档示例"**
  - 📌 **tpc 三层映射**：语法层 = 现 linter（token 级反解析器，svlint 无对应）；
    语义层 = semantic_check 插槽（= svlint SyntaxRule 同构，tpc 的 analyzer 作用域
    链是其超集）；自定义层 = capabilities + 名称检查示例（svlint naming 规则族为蓝本）
  - **可实现性**：名称检查（P1.9 命名约定）直接参照 svlint naming 族——配置扁平化
    （pattern 表）+ kind 分发 + 判定分离，规则代码 ~20 行/条；语义 pass 沿用插槽架构
    补"节点事件遍历"（analyzer 已有作用域链遍历基础）
  - ✅ **P3 声明式规则表已落地（2026-08-28）**：svlint"配置注入 + 判定分离"实证的
    tpc 落地——`[[checks]]` 规则=数据（插件 `rules/*.toml`），引擎零语言知识：
    `core/check_registry.py`（加载/校验 fail-fast：id 重复/severity 非法/pattern
    非法正则/kind 缺失/handler 缺失直接报错）+ `analyzer/checks.py::check_rules_pass`
    （遍历后按符号 kind 分发，re.match pattern 判定，message {var} 插值，L2 handler
    脚本 `file.py:fn` 兜底）。第一个自定义示例 = name_check 插件 NC001-NC010
    （module/instance/wire/reg/port/parameter/localparam/genvar/function/task 十族，
    小写 vs 大写下划线 pattern）。连带修复 4 项：① 语义层符号收集对列表容器节点
    （DeclaratorList 包装的 `items.name` 形态）失效的隐性缺陷（_symbol.py 兜底
    展开 Node.items 列表）——此前所有 DeclaratorList 声明（端口/reg/wire/参数）
    的符号从未进表，语义层符号收集形同虚设；② 端口符号开始收集后暴露 typed_ports
    缺 role 子作用域（master/slave 同名端口在 type 作用域冲突，TypeRole 补独立
    scope）；③ role scope 加入后 flatten_ports 原语只遍历 current_scope 子树漏掉
    type 层符号的 _ref_callbacks（invert 展开残留嵌套 → 变换器过滤空行全丢），
    改从根遍历；④ 非 ANSI 端口方向声明（`output Q;`）与类型声明（`reg Q;`）是
    同一信号两部分——Body*Decl 不再声明符号（方向=属性，类型=符号权威），tv80
    真实语料 E001 清零；⑤ FileManager.load_all_toml 跳过插件 `rules/` 子目录
    （[[checks]] 是 check_registry 数据非语法规则，ext_dirs 直指 plugins 时
    _resolve_peek 崩）+ _resolve_peek 非 dict 防御。tpc check 端到端出 NC 诊断
    （warning 级 exit 0，区间豁免注释同样生效）。
  - ✅ **P4 用户配置层已落地（2026-08-28）**：svlint `.svlint.toml` 逐条 bool
    配置注入的 tpc 落地——`config/tpc_config.json` 的 `checks` 段
    （enabled 不选即关 / overrides severity 提升降级 / per_file glob 豁免），
    `core/check_registry.py::load_user_check_config` 读取 + fail-fast 校验
    （引用不存在的规则 id / severity 非法直接报错），`analyzer/checks.py`
    执行时应用。overrides 提升到 error → `tpc check` exit_code 变 1（门禁
    生效）。per_file 用 pathlib.PurePath.match 尾部语义（`tb/*.sv` /
    `**/tb_*.v`），符号文件来自 ProjectChecker 注入的 `node._file`。
  - ✅ **注释驱动测试框架已落地（2026-08-28）**：Semgrep 式零代码测试的 tpc
    落地——样例源文件内嵌 `// ruleid: X`（必须命中）/ `// ok: X`（不得命中）
    注释，`tests/_check_test.py::run_comment_driven` 运行检查后断言命中集合
    （失败报告带行号与段内诊断）。样例资产 = name_check 插件 `cases/*.sv`
    （新增样例 = 新增断言，规则行为变化时随样例自动更新语义）。
  - ✅ **跨文件名称检查（NC011，2026-08-28）**：svlint module-filename 规则的
    tpc 落地——模块名与文件名一致性，handler 兜底形态（pattern 表达不了
    文件上下文，L2 脚本读 ProjectChecker 注入的 `node._file` 判定）。多模块
    同文件防御：任一模块名匹配文件名即视为文件命名正确，其余不误报；
    全部不匹配才逐个报。单文件 analyze（无 _file）跳过不误报。

- **与 tpc linter 的差异**（各有取舍，非优劣）：

| 维度 | svlint | tpc linter |
|------|--------|-----------|
| 规则载体 | Rust trait 实现（一规则一文件，AST 事件监听） | 反解析器（token 级，复用同一语法 TOML） |
| parser | 复用 sv-parser crate | 自研（语法即 TOML 数据） |
| 规则登记 | build.rs 目录扫描自动登记 | checkers/ 手动导入 |
| 配置 | `.svlint.toml` 逐条 bool + deny_unknown_fields | primitive 配置 + 阶段 code（缺稳定规则命名空间） |
| 测试生成 | testcases/{pass,fail}/{rule}.sv → build.rs 自动生成 #[test] | pytest 单元 + e2e 差分/fidelity |
| 文档生成 | mdgen 自动拼 MANUAL.md（13339 行） | MODEL_INDEX（手工维护） |
| suppress | `/* svlint off/on */` 注释对 | 无（P2.6 规划中） |
| 插件 | libloading 动态库（get_plugin） | capabilities（Python 模块，已实现） |
| 定位 | 单语言 SV linter（190+ 规则） | 通用管线 + verilog/c4 语言包 |

- **可实现性评估（tpc 能否做）**：
  - 🔥 **规则登记自动化**：build.rs 的"目录扫描 → 自动生成配置结构体 + 测试"对 tpc 是
    低成本高价值——checkers/ 现在手动导入，可改为"语法 TOML 规则段声明 + 自动挂载"
    （tpc 的规则=语法资产路线下，规则段即数据，登记天然可自动化）
  - 🔥 **deny_unknown_fields 式 fail-fast 已同构**：tpc ADR-0003 配置 fail-fast 与 svlint
    `#[serde(deny_unknown_fields)]` 同理念（配置写错规则名直接报错，不静默忽略）——
    svlint 是 serde 形态的实证
  - 🔥 **注释 suppress（P2.6 直接参考实现）**：`/* svlint off rulename */` 注释对 +
    Enter Comment 时更新启停表，就是 tpc 计划中豁免机制的最小形态；"textrules 不可控"
    的取舍也值得继承（tpc 的 token 级 lint 相当于"语法规则的 textrules"侧）
  - 💡 **规则命名即分类**：tpc 的语义检查插件（WC001 等）与 linter 阶段 code 可参考
    svlint 前缀约定（style_/naming_/functional），规则类别进规则名，文档/分组自动
  - 💡 **规则参数化**：`[option]` 里 regex/prefix 可配置——P1.9 naming_check 的 pattern
    表可直接参照（正则 + 前缀默认值都在配置里，规则代码只写判定）
  - 💡 **输出三模式**：`--github-actions` 是零依赖的机器可读输出捷径（workflow command
    是文本格式），tpc P2.6 的 `--format json` 之外可加同款低成本模式
  - 📌 **规则集即命令 / MANUAL 自动生成**：tpc 无多规则集需求（单语言包），mdgen 式
    文档生成可观察——tpc 的 MODEL_INDEX 是手工维护，若规则量增长到
    百级可参考"规则代码/配置 + 自动拼文档"
  - 📌 **编码检测 / 多文件 filelist**：tpc 目标 UTF-8 单文件管线（README 边界），观察
  - ⚠️ **避坑**：svlint 复用 sv-parser 虽省 parser 投入，但规则演进受 parser 能力约束
    （已有记录）；tpc 反解析器路线（规则=语法资产）无此问题，是两路线各自成立的取舍

### sv-parser（Rust）— CST 章节镜像 + 生成式节点枚举（2026-08 深调研，dalance 作品链第三站）

- 本地源码镜像：`E:\research\sv-parser`（浅 clone）；调研日期 2026-08-26
- 定位：dalance 的 SystemVerilog parser 库，**完全合规 IEEE 1800-2017 Annex A**；被
  svlint / svls / morty / svinst 四个工具复用（HDL 生态 parser 地基）；481★，MIT/Apache-2.0
- **产出是 CST（Concrete Syntax Tree）而非 AST**：`SyntaxTree { node: AnyNode, text: PreprocessedText }`
  ——保留预处理后文本 + 完整语法树；`RefNode` 变体命名**直接遵循 IEEE Annex A 形式语法**
  （`ModuleDeclarationNonansi`/`AlwaysConstruct`/`ElaborationSystemTask`……"标准即命名"）
- **管线结构**：`parse_sv → pp 预处理器（sv-parser-pp）→ nom 组合子 parser（sv-parser-parser）
  → CST（sv-parser-syntaxtree）`；6-crate workspace（parser / syntaxtree / error / macros / pp / 主库）
- **最大亮点（对 tpc 的组织价值）**：
  - 🔥 **章节 ↔ 目录 ↔ 文件三层镜像**：syntaxtree 与 parser 的 `src/` 下**同章节同名目录
    （source_text/declarations/expressions/instantiations/behavioral_statements/preprocessor/
    specify_section/udp/primitive_instances/general），同名文件一一对应**（module_items.rs /
    package_items.rs / system_verilog_source_text.rs 两边都有）——parser 实现与 CST 节点
    定义按 IEEE 章节同步组织，新增语法特性 = 两边各加一个文件
  - 🔥 **节点结构 ↔ 组合子函数一一对应**：syntaxtree 侧 `#[derive(Node)]` struct 的 `nodes`
    元组（`ElaborationSystemTaskFatal { nodes: (Keyword, Option<Paren<...>>, Symbol) }`）与
    parser 侧 nom 组合子链（`keyword("$fatal") → opt(paren(pair(...))) → symbol(";")`）
    **逐元素对应**——CST 形状即产生式形状，无 AST 转写层
  - 🔥 **build.rs 生成 RefNode/AnyNode 大枚举**（syntaxtree/build.rs）：扫描 src 下所有
    `#[derive(...Node...)]` 注解 → 生成 `RefNode<'a>`（借用）/`AnyNode`（拥有）双枚举 +
    Display——**与 svlint 规则登记同款"目录扫描即登记"**：新增节点类型自动进遍历枚举，
    无需手工维护
  - 🔥 **Node derive 宏**（sv-parser-macros）：自动生成 `Node::next()`（枚举展开变体 /
    struct 展开 nodes 元组）、`From<&Node> for RefNodes`、`From<Node> for AnyNode`、
    `TryFrom<Node> for Locate`（**子 Locate 区间合并收缩**——`unwrap_locate!` 的基础）
  - 🔥 **nom 扩展全家桶集成现场**：`Span = LocatedSpan<&str, SpanInfo>`（nom_locate）+ 
    `GreedyError`（nom-greedyerror，错误位置精度）+ `nom_packrat::storage!(AnyNode, bool, 1024)`
    （记忆化 cache）+ 95 处 `#[recursive_parser]`（nom-recursive 左递归标注，表达式/
    case/声明等递归结构）+ `#[tracable_parser]`（nom-tracable，trace feature gate 编译期
    开关，`fold("number")` 折叠噪音组合子）——**四个 nom 扩展 crate 都是 dalance 自研、
    在此自产自销**，验证了扩展的实战价值
  - 💡 **Leaf = Locate 三元组**（`{offset, line, len}`）：所有非终结符的叶子都是 Locate，
    `get_str`/`get_str_trim`（跳过 WhiteSpace）从节点取原文；`get_origin` 跨文件定位
    （预处理展开后映射回源文件）——tpc Node 缺 token span（TODO P3 前置）的现成参考形态
  - 💡 **空白/注释进树**：`Keyword`/`Symbol` 都带 `(Locate, Vec<WhiteSpace>)`，WhiteSpace =
    Newline/Space/Comment/CompilerDirective 四变体——**CST 保真（注释/空白/编译器指令
    都是树节点）**，与 tpc 注释节点模型（槽位约定）解决同一问题，路线不同
  - 💡 **定界符容器泛型化**：`Paren<T>/Brace<T>/Bracket<T>/ApostropheBrace<T>/List<T,U>`
    （`List { nodes: (U, Vec<(T,U)>) }` + `contents()`）——括号/逗号列表等重复结构是
    泛型类型而非每语法点复制
  - 💡 **EventIter Enter/Leave**：`into_iter().event()` 生成前序遍历事件流（Enter 节点 →
    展开子节点 → Leave），**svlint 规则接口的地基**（SyntaxRule::check 收到的 NodeEvent）
  - 💡 **测试双宏**：`test!(parser, "string", Ok((_, _)))` 断言成功/失败模式 +
    `error_test!(..., 精确位置)` 用 greedyerror 断言**错误落点**——内嵌字符串用例，
    trace feature 可折叠噪音
  - 💡 **"快"的来源是零设计决策**（2026-08 讨论补充）：sv-parser 无文档 dump 自动生成
    脚本（仓库无生成器痕迹），是**手抄 Annex A 产生式 + 机械映射**——CST 形状/命名直接
    照搬标准（零设计决策）、章节镜像目录（组织成本为零）、build.rs 自动登记（接线自动）。
    tpc 的"手写生成式"（TOML production → 引擎推导节点形状）慢在"语言知识进数据"的
    建模成本，为的是换语言不换引擎（verilog/c4 两包验证）；dalance 抄标准为单语言快，
    tpc 资产化为多语言省——各有取舍，维持 tpc 现状（通用与统一优先，机械 dump 不做）
- **与 tpc 的差异**（各有取舍，非优劣）：

| 维度 | sv-parser | tpc parser |
|------|-----------|-----------|
| 语法载体 | Rust 类型 + nom 组合子代码（章节镜像目录） | TOML production（grammar/verilog） |
| 树形态 | CST（保真全部 token/空白/注释） | AST（`[Rule.parser.node]` 形状声明，语言知识留 TOML） |
| 节点登记 | build.rs 扫描 `#[derive(Node)]` 生成枚举 | 从 TOML production 推导类型 |
| 错误处理 | GreedyError 精确位置 | 解析诊断 + lint 诊断 |
| 左递归/记忆化 | nom-recursive + nom-packrat（cache 1024） | 递归下降+回溯+Pratt（end_case 语句边界） |
| 递归结构 | 95 处 `#[recursive_parser]` 标注 | end_case + 回溯组合设计 |
| 位置 | Locate 三元组一等公民 | Node 缺 token span（TODO P3 前置） |

- **可实现性评估（tpc 能否做）**：
  - 🔥 **"目录扫描即登记"已验证同构**：svlint（规则）与 sv-parser（节点枚举）两处都是
    build.rs 扫描目录生成登记代码——tpc 若把 checkers/ 手动导入改为"TOML 规则段声明 +
    自动挂载"，方向已被 sv-parser 二次验证
  - 🔥 **CST 保真路线参考**：sv-parser 的"注释/空白进树"与 tpc 注释节点模型（槽位约定）
    目标一致（保注释/保空白），sv-parser 走"全保真 CST"，tpc 走"AST + 语义归属"——tpc
    的变换路径注释迁移（migrate_comments）正是 AST 路线下比 CST 更优的取舍：结构重写时
    CST 的 WhiteSpace 会随节点丢失，tpc 的语义归属不会
  - 💡 **Locate 三元组**：tpc Node 补 token span（P3.1 前置）可参考 `{offset, line, len}`
    极简形态 + `get_str`（区间切片取原文）——零依赖实现成本低
  - 💡 **章节镜像组织**：tpc grammar/verilog 已按类别分 TOML（typed_ports 等插件目录），
    sv-parser 的"同章节同名文件双镜像"是 parser 与节点定义同步演进的组织范本（tpc 的
    TOML 是单侧声明，无镜像需求，但"语法特性 = 一个目录"的颗粒度可参考）
  - 📌 **nom 扩展生态**：tpc 是自研递归下降+Pratt，无组合子库——nom-tracable（解析 trace
    调试）对 tpc 是路线观察：tpc 若补"解析决策日志"（P3 调试），可参考其 trace 语义
  - 📌 **完整 IEEE 合规**：sv-parser 是"标准 Annex A 全量"路线（CST 节点=标准产生式）；
    tpc verilog 包声明"无 SystemVerilog"（README 边界），不追逐全量合规，各有定位

#### 2005 覆盖核对 — 7 缺口实现对照（2026-08-27 追读，tpc 批次 6 立项参照）

tpc 覆盖核对发现 7 个剩余缺口，逐一追 sv-parser 实现（1800-2017 全量，2005 是其子集，
下列结构在 2005 同形）：

| tpc 缺口 | sv-parser 实现 | 对 tpc 的启示 |
|---|---|---|
| 转义标识符 `\name`（A.9.3，tpc lexer 崩溃） | `identifier = alt(escaped, simple)`——**escaped 是 identifier 第一候选**；`escaped_identifier_impl = tag("\\") + is_not(" \t\r\n")`（反斜杠后到空白止） | 🔥 词法层并入 identifier（非独立 token 类）；tpc 需 lexer 支持 `\` 起始 id + 规则/渲染透传 |
| library 声明（A.1.1） | **独立顶层入口** `library_text = many(library_description)`；description = library_declaration \| include_statement \| config_declaration；`library_declaration = library id (, file_path)* [-incdir ...] ;`，file_path 用 `is_not(",; ")` 宽松捕获 | 💡 tpc config 插件只做了 config 声明，library 需独立入口（含 `-incdir` 与 `include` 语句） |
| continuous assign strength/delay（A.6.1） | **拆两分支**：`continuous_assign_net = assign [drive_strength] [delay3] 网络赋值列表 ;` 与 `continuous_assign_variable = assign [delay_control] 变量赋值列表 ;`——strength/delay 是可选前缀，复用共享 strengths.rs/delays.rs | 🔥 tpc AssignStmt 只裸 `assign`；strength 6 形态（01/10/0z/1z/z1/z0）nettypes/gates 已有同名规则可直接复用 |
| always 无事件控制（A.6.2） | `always_construct = always_keyword + statement`——**event_control 不是 always 的一部分**，`always #5 ...`/`always begin...end` 的时序/块由 statement 承载 | 🔥 tpc AlwaysStmt 强制 `@EventControl`；应按标准放宽为 `always statement`（时序进 statement 层） |
| 单索引 range `[3]`（A.2.5） | `unpacked_dimension = alt(range, constant_expression)`——`[a:b]` 与 `[3]` 显式两分支 | 🔥 tpc Range 强制 `[a:b]`；补单表达式分支（声明维与位选 SelectSuffix 已有 `a[3]` 形态） |
| genvar 列表（A.4.2） | `genvar_declaration = genvar list_of_genvar_identifiers ;`，list = 逗号分隔 | 💡 tpc GenvarDecl 只单标识符；补 `(, @Identifier)*`（同 DeclaratorList 模式） |
| 实例/门级 attribute 前缀（A.4.1/A.3.1） | **attribute 在模块项层**：`module_or_generate_item_{module,gate,udp,module_item,parameter}` 五分支各包 `many0(attribute_instance)`，而非塞进 instantiation 内部；port connection 层另支持 attribute | 🔥 tpc attributes 插件只挂声明/语句；应按 A.1.4 `{ attribute_instance } module_or_generate_item` 在模块项各分支前缀挂 |

- **共性观察**：sv-parser 对"可选修饰前缀"（strength/delay/attribute）一律在**产生式层用
  `opt`/`many0` 前置**，不改被修饰规则内部；tpc 同构做法 = 在 production 首元素加
  `@AttrInstance?`/`@DriveStrength?` 等，无需动引擎
- **转义标识符是唯一 lexer 层缺口**（其余 6 个都是规则层）：sv-parser 在词法并入
  identifier，tpc 需在 lexer 增加 `\` 起始 id 分支（当前 `\` 抛 ValueError 崩溃，非软失败）
- 出处：`sv-parser-parser/src/{general/identifiers.rs, source_text/library_source_text.rs,
  behavioral_statements/continuous_assignment_and_net_alias_statements.rs + procedural_blocks_
  and_assignments.rs, declarations/{declaration_ranges.rs, declaration_lists.rs, type_declarations.rs},
  instantiations/module_instantiation.rs, source_text/module_items.rs}`

#### sv-parser 差分对标（2026-08-27 落地，第二参照系）

- **工具链**：Rust 装到 `D:\rust`（rustup + stable-x86_64-pc-windows-gnu，
  因本机 VS BuildTools 的 Windows SDK 桌面库缺失 kernel32.lib、msvc target
  无法链接，改用 GNU host+target 全链路）；parse_sv.exe 编译自 sv-parser
  仓库 `examples/parse_sv.rs`，44MB，放 `tests/differential/.tools/sv-parser/`
  （.gitignore 忽略，与 verible 同机制）
- **门禁脚本**：`tests/differential/run_differential_svparser.py`，三属性：
  1. **接受域**（假拒检测）：sv-parser 接受 ∧ 2005 子集语料 → tpc 必须接受
  2. **宽进差异**（记录非失败）：sv-parser 拒 ∧ tpc 收——sv-parser 严格
     实现 Annex A（如 `wire \a.b;` 须写 `\a.b ;`），tpc 分隔符提前终止
     直接可解析，是有意取舍；tpc 专属增强语法（typed_ports 的 impl/type）
     sv-parser 不认也归此类
  3. **互操作**：tpc 输出必须被 sv-parser 接受（渲染器产出合法代码）
- **基线（2026-08-27）**：92 文件 → false-reject 0、bad-interop 0、
  lenient-diff 3（全为 samples/transform 的 typed_ports 增强语法样本）
- **与 Verible 差分的关系**：同为"语料限定 2005 子集"的接受域检查；sv-parser
  增量价值 = 纯解析器（Verible 是 formatter）+ 严格 Annex A 暴露宽进差异
  （实测 escaped_identifier 严格/宽进分歧已由 probe 验证）
- **real corpus 门禁拆分（2026-08-28）**：`test_svparser_accept_domain_and_
  interop` 拆为 accept-domain（假拒检测，仅无宏文件）与 interop（tpc 输出→
  sv-parser，覆盖全语料）——宏文件互操作半边此前整体跳过，实测 picorv32/
  ice40 输出 sv-parser 可接受（纳入门禁），darkriscv/tv80 豁免（见下）

#### SV 全量规模估算（2026-08-27，verilog-2005 全量后的延伸研判）

- **实测口径**：verilog 包现 259 条 parser 规则（核心 144 + 插件 115，
  typed_ports 增强 16 条）覆盖 1364-2005 Annex A ≈110-120 条生产式 →
  规则/生产式比率 ≈2.3（含子规则/分发器/节点绑定）
- **sv-parser 侧**：CST 节点 1057 个 enum variant ↔ 1800-2017 Annex A
  ≈450-500 条生产式 → SV 全量折算 tpc 规则 ≈1050-1150，净新增 ≈800-900 条
- **加速因素**：基建已付（block/inline/inject/FOLLOW/linter 消歧/renderer
  DSL/差分工具链）；sv-parser 差分即 oracle，覆盖驱动是"喂语料→修误拒"
  机械循环；~40 种 SV 标识符由通用 Identifier+语义层吸收，边际成本≈0；
  边际速率 35-45 规则/周（均值 30 被前期基建拉低）
- **减速因素**：SVA（assertion 声明+语句 ≈100+ 节点，自有运算符族
  `##`/`[*]`/`[->]`、局部变量、递归属性——需新 pratt 族 + linter 消歧，
  per-规则成本 ×1.5-2）；类型系统（net_and_variable_types 67 + type_
  declarations 27 + class_items 32，交叉引用深）；SV 预处理器扩展是引擎级
  工作；歧义战场（cast-vs-ternary、`'{}` vs 拼接、接口作用域）会重演
  typed_ports `.` exclude 战役
- **结论**：语法层全量（sv-parser 差分全绿 + lint recall 保持）8-12 个月；
  阶段 A SV 核心子集 3-4 个月；SVA/class/constraint 是最大三块。对照：
  sv-parser 作者单人从零做到 1800-2017 全量花数年——我们有配置化基建 +
  差分 oracle，速度不是一个量级，但语言复杂度体量实打实
- **口径边界**：以上只到语法层（解析接受 + CST），不含 analyzer 语义层
  （类型检查/约束求解）——sv-parser 本身也只到语法层
- **决策**：2026-08-27 缓行，先玩熟 verilog 全量；立项触发后再细化阶段 A 缺口清单

#### 真实语料实测（2026-08-27，real corpus 回归基线）

- **语料**：`tests/e2e/samples/real/ref/` 扩至 9 文件（归属/许可见 CREDITS.md）：
  CPU 核 4（darkriscv/picorv32/serv_top/tv80）+ UART×3（alexforencich，MIT）+
  simcells（yosys，ISC，149 个 UDP/门级仿真单元）+ ice40_cells_sim（yosys，
  ISC，specify 时序块，**默认配置**——端口默认值宏 M1 闭环后无需
  NO_ICE40 预定义，见下文）。回归基线 `tests/e2e/test_real_corpus.py`：
  全量管线 + lint 零诊断 + 幂等 + module 数下限（防静默截断）+ token
  保真度 ≥0.80 + sv-parser 差分门禁（无宏文件：假拒 + 互操作）
- **实测暴露的 4 个缺口（全部修复）**：
  - 🔥 **`===`/`!==`（A.8.4 case_equality）全缺失**：`base/_token.toml`
    无 token、CmpOp 无算子、`_symbol_level.toml` operator 表无条目——三处
    都要补（linter 的 ExpressionChecker 走 operator_defs，parser 走 CmpOp
    规则，lexer 走 extend 表）。ice40 大量使用
  - 🔥 **多目标连续赋值（A.6.1 list_of_net_assignments）真实代码实证**：
    ice40 ~17 处 + yosys techmap；批次 6 因 linter 误判延后，现以独立
    `AssignExtra` 子规则（`,` target `=` value，自带渲染器）落地，与
    单目标/strength/delay 前缀共存
  - 🔥 **模块头属性（A.1.1 `{ attribute_instance } module_declaration`）**：
    attributes 插件新增顶层 `AttrModuleDecl`（@AttrInstance @ModuleDecl|
    @MacroModuleDecl，start token `(`，与 ModuleDecl 的 module 关键字不冲突）
  - 💡 **语句体宏行尾补分号**：非空 body 宏独占一行无分号（ice40
    `` `SB_DFF_INIT``，body=`initial Q = 0;`）展开为裸 `tpc_marker_N`，
    裸 id 非合法语句（lint/parser 双拒）。修法：行尾（调用后仅空白）时
    替换文本补 `;` → `tpc_marker_N;` 按 A.6.9 裸任务调用可解析；anchor
    marker 保持无分号（还原正则 `\b` 在 `;` 前成边界）。已验证对既有
    语料零影响（表达式位宏不触发）
- **审查补漏（2026-08-28，对 d9024e0 的复查）**：
  - 🔥 **formatter column_align 拆散 `!==`**：对齐 pass 的 `_tokenize_
    bracket_aware` 只合并连续等号（`==`/`===`），`!==` 的 `!` 进 buf、
    `==` 单独成 token → 重组为 `d ! == e`（破坏运算符语义，输出会被
    sv-parser 拒）。修法：等号序列前导 `!` 弹出并入（`!=`/`!==` 单 token）
    + 对齐场景回归测试。批次 7 测试未抓到的原因：单行场景不触发列对齐
- **语料前沿（已修复，2026-08-28 批次 10 / M1）**：
  - 🔥 **端口默认值宏**：`input NAME `M`（body=`= 1'b1`）此前 token 替换顶掉
    端口名——ice40 默认配置 lint 报 34 错，只能走 NO_ICE40 空宏（注释锚）
    规避。修法（预处理器锚形态再设计，`_expand.py` + `_bridge.py`）：
    赋值后缀宏（body 以 `=` 开头）改 **inline+body 区间还原**——展开时
    marker 注释 + body 原文保留在源码（parser 跳过注释看到 `input NAME
    = 1'b1`，Declarator @Init? 兜住端口默认值），还原时按 [marker..body]
    区间替换回宏调用原文残片。**渲染行尾锚定实证**：渲染端把 marker 挪到
    行尾（`= 1'b1 /*<marker>*/,`），与"marker 后找 body"原文顺序相反——
    inline 分支补"marker 前同行 rfind body"定位。ice40 默认配置全管线
    success + lint 零诊断 + 43 处宏使用（含 `ICE40_DEFAULT_ASSIGNMENT_V(v)`
    带参形态 6 处）全还原 + sv-parser 互操作接受（sv-parser 自己展开
    `= 1'b1` 端口默认值，1800 合法）。语料门禁改为默认配置
    （test_real_corpus.py / run_all_tests.py 预定义清空）。
  - 📌 **yosys 内部 `$cell` 名**：`module $demux` 类（techmap）非 2005/1800
    Annex A 合法输入（sv-parser 同样拒），techmap 已排除出语料
- **多目标 assign 坏输入收敛（2026-08-28 已修，见「引擎增益：坏输入收敛」）**：
  `assign a = ;` / `b + ;` 曾 ~978 条重复诊断（同一区间节点递归注册至
  Python 递归上限），现收敛到 1-3 条精确诊断（phase-expr/phase-statement），
  漏检样本 `assign = b;` 同时检出

#### A 类缺口修复（2026-08-28，test_2005_batch8.py）

- **层次化 id 表达式位（A.9.3 hierarchical_identifier）**：此前 `a.b` 在
  表达式/赋值位 lint 拒——`HierId` 只在 specify/defparam 存在，表达式原子
  未接。修法：`05_expressions.toml` 新增 `HierExpr` 原子（`@Identifier
  (dot,@Identifier)* ([suffix])*`，成员链 + 下标链），PrimaryExpr choice 中
  置于 SelectExpr 之后（`a[0]` 优先 SelectExpr，`a.b` 走 HierExpr）；
  renderer 用 HierId 同款 `join="."`（parts 含 head，防 `a.b` 渲染成 `ab`）
- 💡 **typed_ports 共存验证**：表达式位新增 `.` 能力后，端口列表类型引用
  （`spi.slave spi_io`）不受影响（声明位 exclude 消歧仍生效，test_typed_ports
  8 例全过）——批量回归的必要检查点
- **交错形态形式化宽进（2026-08-28 追加，test_2005_batch9.py）**：`a[0].b` /
  `a.b[0].c` / `mem[i].field`（成员与下标任意交错）此前记录"超 2005 暂不
  支持"，按"tpc 只做形式化解析、继承链语义解析不承担"的定位改支持。实现
  三件套：① HierExpr production 改交错（`@Identifier (@HierMember|@HierSuffix)*`，
  HierMember 渲染 `.b`、HierSuffix 渲染 `[0]`，parts 空分隔 join 保序——
  纯 TOML 声明，引擎零硬编码）；② SelectExpr `exclude = ["symbol.base.dot"]`
  （纯下标不吞成员访问，回滚给 HierExpr；Verilog 无 `.` 运算符，误伤面为零）；
  ③ 原子**最长匹配**（parser._atom_parser_impl + linter match_atom：遍历全
  部 is_atom 规则取消费最多者，等长取先——`a[0]` 纯下标仍走 SelectExpr，
  AST 形状稳定）
- 🔥 **连带修复既有缺陷（lookahead Level 2 候选集）**：`always @(*) a.b <= x;`
  （NBA target 为层级引用）此前误判未识别——Level 1 判别路径被 `.` 挡住、
  path 候选全淘汰，而 l2_only 分支只试 `path_entries + l2_only`（path 已空
  → 漏掉被淘汰的真候选 NBA）。修法：l2_only 分支改试**原始 entries**（试
  解析取"错误最少 + 消费最多"者，errs=0 的静态正确候选天然胜出，不依赖
  候选顺序）。L356 无条件回退（allow_partial=False）保持不变——if 缺括号
  等静态可判别多候选仍报未识别（e09/e17 门禁基线），拼错语句（`foo bar;`）
  仍走 Level 2 报未识别（不吞错）
- **无括号系统任务语句（A.6.2/A.9 sys_task_enable）**：SysTaskStmt 括号
  整体可选（`$ name (args?)? ;`），`$finish;`/`$stop;` 可解析；args 绑定
  `$3.sub_node[0].sub_node[1]`（opt 组解包，同 MintypmaxExpr 模式）；
  `$display(...)` 带参形态回归
- **参数覆盖 mintypmax（A.4.3/A.8.2）**：`#(.P(1:2:3))` 此前挂（974 lint
  病理）——NamedParamOverride 值位 `@Expression` 改 `@MintypmaxExpr`
  （nettypes 插件，expr [ : expr : expr ]，单值天然兼容）；位置参数
  `#(Mode)` 保持 @Expression
- **核对澄清**：三元 `?:`、过程体 event/localparam、命名块头声明经实测
  **已支持**（TODO 摘要误列）——清单以实测为准

#### S 级修复批次（2026-08-28，interop 门禁拆分 + pratt 吞注释）

- **interop 门禁覆盖宏文件（P1.5）**：`test_svparser_accept_domain_and_interop`
  拆为两门禁——accept-domain（假拒检测）仅无宏文件（两边预处理器语义不同，
  不构成对拍样本）；interop（tpc 输出→sv-parser）覆盖全语料（tpc 自渲染
  文本由 sv-parser 自己的预处理器再处理，宏结构合法即接受，实测 picorv32
  123KB / ice40 167KB 输出全过）。豁免 2 文件（`_SVPARSER_INTEROP_SKIP`）：
  tv80（sv-parser 源侧解析失败 3768:7 `else`，对拍不可靠）+ darkriscv
  （见下缺陷）
- 🔥 **宏展开路径条件编译还原不完整（darkriscv，interop 暴露，2026-08-28 修复）**：
  darkriscv 源 sv-parser 接受（101 `ifdef` + 177 `define`），tpc 输出被拒
  （Preprocess 错误）——输出 `ifdef` 曾仅 89 个，缺 12 个全为**未定义条件**
  （__INTERRUPT__×3 / __COPROCESSOR__×2 / __EBREAK__×2 / __DBNZ__×2 /
  __CSR__×1 / MODEL_TECH×1 / SIMULATION×1）。三层根因：① tpc 占位注释在
  渲染中被 pratt/line 通道收集后，restore 的退化分支 target 行被占则**静默
  丢失**（条件块整块消失）；② 相邻占位锚互相引用（后块锚 = 前块占位文本）
  导致独立插值**顺序错乱**（端口组 INTERRUPT/SIMULATION/COPROCESSOR 互换）；
  ③ 嵌套块头/块尾占位（如 __RV32E__ 的 endif）独立插值时锚点静态、块头
  插入后未更新 → **块尾错位**。修法（inline_comment.py 4 项通用改进）：
  tpc 占位不静默丢失（退化强制独立行插入）+ 相邻标记顺序插入（源行距 ≤8
  跟随上次插入）+ 插入后动态更新插值锚点 + 循环级 center 初始化。**结果：
  ifdef 101/101 全还原、无占位残留、lint 零诊断**；残余：表达式链内相邻
  条件块（IFPC 三目链 EBREAK/INTERRUPT/DBNZ）还原位置依赖插值（渲染行距
  非线性 + 锚点稀疏），嵌套位置仍有偏差 → sv-parser 仍拒（interop 豁免
  保留）。根治需 active 内容 marker 化（_flush_block 改造）或 token span
  映射（P3.1 前置），另案。
- **pratt 前缀吞注释（P1.5 修复）**：pratt 前缀位置把 COMMENT 当续行分隔
  跳过（`a + /* c */ b` 的 `/* c */`、`- /* c */ a`、`cond ? /* c */ a : b`
  静默丢失，不进任何通道）。修法：`parse_with_count`/`parse_expression`
  增 `comment_sink` 回调（语言无关，默认 None），前缀跳注释时记录
  `{anchor: 注释前 token, text, line, midline: True}` 条目进 parser
  `_comment_anchors`——渲染后 restore only_midline 回插（注释节点模型 2b-2
  兜底路径，与 `assign b = /* 嵌入 */ rst_n` 的 inline_after 双轨互补；
  `=` 等文本锚场景渲染端可直接消费，pratt 表达式内无文本锚场景走回插）。
  实测 5 形态保留（中缀后/赋值 RHS/一元前缀/三目分支/case 表达式），
  `a /* c */ + b`（中缀前，外层机制收集）回归守卫
- 📌 **同行多注释局限（既有边界，非本次引入）**：`cond ? /* 真 */ a :
  /* 假 */ b` 同行两注释受 restore 单行单插局限（第一条占行后第二条退化
  行尾）——修复前 pratt 吞注释是直接丢失，属能力边界，记录不修

#### 测试隔离机制（2026-08-28，顺序无关从机制上修复）

- **背景**：引擎多处全局可变单例，同一进程多语言/多配置测试顺序导致状态
  残留污染——此前靠各测试"独立 GrammarRulesRegister() 实例"逐处 workaround
  （c4/sim_plugin/analyzer 5 处），仍偶发顺序敏感（批次 5/6 全量 intermittently
  挂 test_error_category_always_hit 等）
- **全局状态清单**：GrammarRulesRegister._default_instance（注册表只增不重置）、
  ConfigRegistry 类变量（_entries/_loaded/_entries_source/_sources/_resolved +
  load_all 推送进各模块的 _xxx_cfg 模块变量）、plugin_loader
  （_loaded_components/_transform_slots/_PRIMITIVE_ORDER，含 Python handler
  module 引用）、pipeline._PIPELINE_SHARED、ProjectChecker._SHARED
- **机制**：`core/global_state.py` snapshot()/restore()——session 基线
  fixture 拍 verilog 快照，每测试后 autouse restore 还原。轻量状态 deepcopy
  （注册表 ~2.5ms + 配置 ~2ms/测试），共享缓存 clear 重建
- 🔥 **共享引用污染教训（实测复现）**：restore 把快照对象**直接赋给全局**
  时，下一测试原地 clear/改写全局（isolated_registry 的 ConfigRegistry.
  reset() 即清空共享引用）→ **污染快照对象本身**，后续 restore 还原的是被
  污染的快照（现象：cfg_loaded 变 0 项、_entries 变 1 项）。修法：restore
  一律 deepcopy 再赋值，快照保持不可变
- **连带清理**：test_config_loading 的 isolated_registry 旧 workaround
  （手动 save/restore 三字段，漏 _entries_source，且与新机制时序交错）删除，
  统一走 autouse 还原；pipeline._config_loaded 全局标记（第一个语言决定配置）
  改 rules_dir 键控
- **验证**：双向顺序（c4→verilog / verilog→c4）278 测试结果一致；
  全量 1222 passed + 6 skipped；子集组合（core+classifier 曾挂）73 passed；
  c4 等"独立实例"workaround 保留无害（机制兜底）

#### 引擎增益：消歧 trace + 候选集契约（2026-08-28，a[0].b 修复复盘驱动）

- **动机**：交错形态修复暴露的 3 个引擎缺陷（match_atom 首个命中、lookahead
  l2_only 候选集、`a.b <= x` 误判）全是**消歧/匹配策略层**的隐式协议——定位
  全靠手动脚本复现 + monkeypatch 打印，成本高。复盘结论：语法知识已数据化，
  **解析策略层是下一个该增益的面**（消歧/匹配/恢复仍是引擎代码里的隐式协议）
- **消歧决策 trace（linter/lookahead.py）**：`[lint-trace]` 输出到 stderr——
  classify 入口（token/候选集）、Level 1 每步（seen 序列/kept/dropped/分支
  决策：命中/回退/break）、Level 2 每候选（errs/consumed/first_err）与 best
  选择。开关：构造参数 `trace`（LookaheadTable/Discovery/LinterScanner 透传）
  或环境变量 `TPC_LINT_TRACE=1`（模块导入时读取，进程启动设置）。默认关闭
  零行为影响。与 parser 的 set_trace 同风格，定位 classify 非预期返回时
  一眼看到淘汰过程
- **消歧候选集契约测试（test_linter_lookahead.py TestLevel2CandidateSet）**：
  固化语义意图——`a.b <= x` / `mem[i].field <= x`（操作数内部 token 挡判别
  路径）→ 仍分类为 NBA；`a[0].b = 1` → BlockingAssign；`a <= x` / `a = x`
  无遮挡时 Level 1 静态判别仍生效；`assign a = b` 缺分号（A 类）→ allow_
  partial 返回候选（checker 报精确诊断）；`foo bar` 拼错（B 类）→ [] 未识别
  （不吞错）。行为快照之外的语义意图层，防同类回归

#### 引擎增益：坏输入收敛（2026-08-28，discovery 递归爆炸根治）

- **现象**：`assign a = ;` / `b + ;` 产生 ~978 条诊断，其中 977 条是重复的
  `unexpected 'assign'`（同一区间节点注册 ~978 次）
- **根因链（三层，逐层定位）**：
  1. **inline 语句分派器自递归**：SimCtrlStmt（inline 分派器，production 单
     choice of 9 个语句规则）被判嵌套容器，`_locate_stmt_body` 返回 body
     起点 == 规则起点（choice 第一分支 ForkBlock 是块）→ 递归区间与自身
     完全重叠 → 每层注册同一节点直至 Python 递归上限（~978 层）。修法：
     body 起点必须**严格在规则起点后**（`i < bs < e`）+ `_discover_range`
     递归深度上限（`_MAX_DISCOVER_DEPTH=64`，纵深防御）
  2. **假推进胜出**：allow_partial 的 best 选择用 consumed 加分，但错误恢复
     的 skip 推进是假推进——SimCtrlStmt（choice 失败 strict 报错+跳过 1
     token）consumed=1 胜过 AssignStmt（表达式失败不推进 consumed=0）。
     修法：consumed 加分仅作用于 errs==0（完整匹配），errs>0 保持注册顺序
  3. **inline 分派器候选噪音**：SimCtrlStmt 的 first = 9 分支 first 并集，
     `assign` 触发它；choice 内 strict=False 使 ProcAssign 的 @PrimaryExpr
     失败不推进、后续元素继续 → 假成功（errs=0），`assign = b;` 被误分类
     漏检。修法：inline 分派器不注册为消歧候选（分支各自 is_statement 已
     注册）；grammar_slicer 补提取 inline 字段
- **验证**：`assign a = ;` 978→1（phase-expr）、`assign = b;` 0→3（检出）、
  `b + ;` 978→1；lint accuracy 31/31 0 FP 保持（e08/e10/e11/e16/e22 全 HIT）；
  契约测试 TestDiagnosticConvergence（诊断数量有界）+ 正常输入零诊断
- **后续候选**：per-rule 匹配策略声明化（最长匹配从引擎全局默认变成配置可
  表达）、matcher._probe_eof 试探语境状态治理、错误恢复的 strict=False
  "失败不推进但后续元素继续"容错语义（假成功的深层机制，本次以分派器排除
  规避，未根治 matcher 层）

#### 多后端输出设计（2026-08-28 定稿，P4.1 蓝图）

- **问题**：当前渲染器体系"一套配置一套输出"——transform 串行覆盖主 AST
  （`ast = plugin.process(ast)` 链式，第一个后端插件产出 AsmProgram 后，
  第二个后端插件看到的已非源 AST）；布局是单一命名空间（load_layouts 按
  节点名合并）；mark_extra 只能从已变换 AST 取子树，不能从源 AST 独立变换
- **定稿方案：后端 = 同构渲染器实例**（用户设计，比旁路插件+mark_extra 更
  彻底）——插件系统实例化特定后端的渲染器，与主管线渲染器**同一个 Renderer
  类**（零引擎分裂，仅布局配置不同）；语言配置留在插件目录；主管线渲染器
  只负责主 AST 原样打印
- **现状支撑**（已验证）：Renderer 已是可实例化类（`Renderer(rules_dir)` →
  load_layouts → render，零语言特定代码）；load_layouts 递归 rules_dir 含
  plugins/ 子目录（插件布局声明机制已存在，缺"作用域"）；mark_extra/
  collect_extra_asts 多文件输出雏形已有
- **引擎补丁 3 处**：① `Renderer.__init__` 加 `layout_dirs` 参数（插件级
  布局目录后加载）；② plugin_loader 识别旁路后端插件（tpc.toml
  `[transform] target = "llvm"`）→ 实例化同构渲染器（布局=插件目录）；
  ③ 旁路插件 process 基于**源 AST**（transform 前干净形态）→ 产物节点交
  自己的渲染器 → 独立文件输出（复用 mark_extra 通道）
- **配置不复杂保证**：复杂度 = O(插件数)——主管线零改动（无旁路插件时行为
  与现状一致）；新增后端 = 一个自包含插件目录（transform handler + 布局
  声明 + target），不给主规则配后端布局；后端节点族节点名与主 AST 不重叠
  （AsmProgram/LLVMProgram 等），布局命名空间天然隔离
- **待拍板**：旁路后端默认全部输出（零配置）vs 引入 `--backend` 选择参数
  ——倾向先全部输出，按需选择等真实需求再加

#### UDP 处理专题（2026-08-27 追读，P1.8 UDP 立项的落地参照）

- 出处：`sv-parser-parser/src/udp_declaration_and_instantiation/`（udp_declaration /
  udp_ports / udp_body / udp_instantiation 四文件）+ syntaxtree 同名镜像
- **table 无"行文本"特殊机制**（对 tpc 最关键的实证）：`CombinationalEntry =
  LevelInputList ":" OutputSymbol ";"`、`SequentialEntry = SeqInputList ":"
  CurrentState ":" NextState ";"`，body = `keyword("table") → 首条 entry →
  many_till(entry, keyword("endtable"))`——**分号终结符消解行边界**，换行/空白
  只是词法间隔。修正此前"UDP table 需引擎新增原始行规则"的评估：tpc 的
  production 重复（`@Entry+`）+ FOLLOW 即可表达 many_till 形态，无需引擎改动
- **表符号逐字符硬编码**：`symbol("0"/"1"/"x"/"X"/"?"/"b"/"B"/"r"/"R"/"f"/"F"/
  "p"/"P"/"n"/"N"/"*")` 全部枚举大小写变体（level_symbol/edge_symbol 的 alt 链）；
  init_val 甚至把 `1'b0/1'b1/1'bx/1'B0/1'BX...` 全变体硬编码为 keyword。可行的
  前提是 **parser 输入是字符流（Span = LocatedSpan<&str>），无词法层**——不存在
  "b 是 identifier"的词法身份问题；这是手写 parser 的机械笨拙面
- **声明形态**：`primitive name (ports) ; → 端口声明 → table...endtable →
  endprimitive [: name]`；SV 变体（extern/ANSI/wildcard）超出 1364-2005 范围，
  tpc 只需 nonansi 一条路径
- **实例化形态**：`udp_identifier [drive_strength] [delay2] instance (, instance)* ;`，
  位置连接 `(output, input...)`——**与门级原语共享 drive_strength/delay2 定义**，
  印证 tpc 把 UDP 与门级原语同批立项、先落 strength/delay 规则的顺序
- **对 tpc 的启示**：
  - 🔥 **UDP 是结构化 token 规则，不是引擎难题**：tpc 的 production 可直接表达
    `[UdpBody] table → @Entry+ endtable`、`[CombEntry] @LevelSymbol+ : @OutputSymbol ;`
    形态——真正的设计点收窄为一个：**表符号的词法身份**
  - 💡 **token 流 vs 字符流的范式差（tpc 特有）**：tpc 是 token 驱动——`0/1`
    （literal.number）、`? * - : ;`（symbol.base 现成 token）直接引用即可；唯
    **裸字母 b/r/f/p/n/x 是 id token**。候选方案立项时定：(a) production 字面
    token 增加 content 约束（`id.id` + 内容 ∈ 单字符集）；(b) 接受宽进
    （UDP 上下文 id 即表符号，lint 兜底报 warning）——比"行文本解析"小得多
  - 💡 **init_val tpc 反而更优**：sv-parser 的 `1'b0` 全变体 keyword 硬编码在
    tpc 由 based number token 天然覆盖（大小写/宽度变体零枚举）
  - 📌 **参考粒度**：UDP 实例化的 `[drive_strength] [delay2]` 前缀与 specify 的
    路径延迟共享——strength/delay 是 A.2.2.2/A.2.2.3 的独立资产，先于 UDP 落地

### svls（Rust）— "检查器 → LSP"的最薄封装（2026-08 深调研，dalance 作品链第四站）

- 本地源码镜像：`E:\research\svls`（浅 clone）；调研日期 2026-08-26
- 定位：SystemVerilog language server（583★，tower-lsp），**唯一功能是把 svlint 变成 LSP**
  （README 直白："Linter based on svlint"）；配套 svls-vscode（VSCode 客户端）
- 核心形态（最大价值）：`backend.rs` 仅 363 行，`lint()` 函数**库级复用 svlint::linter**
  （`Linter::new` + `textrules_check` + `syntaxrules_check` → `LintFailed` → `Diagnostic::new`），
  不是封装命令行——**这是 references.md 里 hdl_checker 研判"LSP 服务化是 pylance 式体验
  最终形态"的更纯粹实证**（hdl_checker 封装外部工具输出，svls 直接复用库 API）
- 配置双文件：`.svls.toml`（`[verilog] include_paths/defines/plugins` + `[option] linter` 开关）+
  `.svlint.toml`（规则配置，initialize 时分层搜索）；linter 配置失败降级 `enable_all()`
- 诊断映射：`LintFailed` → `Diagnostic`（WARNING + 规则名作 code + source "svls"）；
  解析错误 → ERROR；`did_open/did_change` 全量同步 + `publish_diagnostics`
- **可实现性评估（tpc P2.6 直接参考）**：
  - 🔥 **接口形态**：`lint(text, path) -> Vec<Diagnostic>` 就是 LSP 化的全部接口——tpc
    `tpc-check` 若做 LSP，把诊断模型设计成"位置 + 规则名 + 提示"即可薄封装（tower-lsp
    是 Rust，tpc 零依赖下 stdlib 手写 jsonrpc 约几百行，references.md 已记）
  - 💡 **配置降级策略**：linter 配置解析失败 → 降级 enable_all + 弹警告，而非崩溃——
    tpc ADR-0003 是 fail-fast 硬约束，此处"编辑器场景降级"与"CLI 场景 fail-fast"各有取舍
    （编辑器里配置坏了不该打不开文件）
  - 📌 **薄封装验证**：svls 证明"成熟检查器 + 极薄 LSP 壳"是可行形态（3 个源文件），
    tpc 若做服务化可保持检查器与 LSP 解耦，壳只做 Diagnostic 翻译

### flexlint（Rust）— 正则规则 lint（2026-08 深调研，dalance 早期作品）

- 本地源码镜像：`E:\research\flexlint`（浅 clone）；调研日期 2026-08-26
- 定位：**规则 = TOML 正则的通用 lint**（28★，2018 年早期作品，0.2.7），无 parser——纯
  正则匹配 + glob 文件遍历，验证"正则规则"路线的极限
- **规则四元组 + 位置断言**（`src/lint.rs`）：`pattern`（匹配触发）+ `required`（`find_at`
  位置断言：匹配点必须命中 required）+ `forbidden`（匹配点不得命中）+ `ignore`（区间跳过，
  例：`(/\*/?([^/]|[^*]/)*\*/)|(//.*\n)` 注释豁免）+ `hint` + `includes/excludes`（glob）
- **CheckedState 四态**：Pass / Fail / Skip（ignore 区间内）/ Unmatch（无匹配）——
  四态显式建模，与 tpc lint 的"命中即报"不同，Unmatch 可表达"规则没触发"的语义
- 输出双模式：simple（单行）/ pretty（rustc 风格，svlint printer 前身）
- **第三种 lint 形态对照**（各有取舍，非优劣）：

| 维度 | svlint | flexlint | tpc linter |
|------|--------|----------|-----------|
| 规则载体 | Rust trait（AST 事件） | TOML 正则四元组 | 反解析器（token 级，语法 TOML） |
| parser | sv-parser CST | 无（纯正则） | 自研（语法即数据） |
| 表达力 | 结构感知（树/上下文） | 正则（行内/区间） | token 序列模式 |
| 注释豁免 | `/* svlint off */` 注释对 | ignore 正则 | 语法结构判定 |
| 定位 | SV 专用 190+ 规则 | 任意文本通用 | SV/c4 语言包 |

- **可实现性评估（tpc 能否做）**：
  - 💡 **ignore 正则即 suppress 的第三种实现**：svlint 用注释对（用户显式豁免）、
    tpc 用语法结构判定（注释挂树）、flexlint 用 ignore 正则（规则内声明豁免区间）——
    P2.6 做豁免机制时三种形态可并列参考
  - 💡 **required/forbidden 位置断言**：`find_at` 起点断言是"正则 + 上下文"的低成本
    组合，tpc 若做"规则 = 声明式 pattern 表"（P1.9 naming_check 方向）可参考其
    pattern + 断言分离的字段设计
  - 📌 **纯正则极限**：flexlint 验证了正则规则的表达能力边界（跨行/嵌套/结构匹配
    做不到），tpc 反解析器路线（token 级）比它强在结构感知——flexlint 是"最简
    规则即数据"的基线参照

### 静态检查工具群补充——svls/flexlint 与 tpc 的完整对照

（svls/flexlint 详情见上文两节，这里补充"服务化"维度的三形态收束）：
- **hdl_checker**（封装外部工具 → LSP）vs **svls**（库级复用 → LSP）vs **tpc 现状**
  （CLI 文本）：三者对应"检查服务化"的三个渐进形态——封装命令 / 复用库 / 内建管线。
  tpc 的零依赖内建管线形态上最接近 svls（自己就是检查器），若服务化只需补 LSP 翻译层

### 注入 vs 替换机制研判（2026-08-29，C 标准插件族设计触发）

- **触发**：C 语言包按"标准插件族"设计（ROADMAP）——c11/c17/c23 增量插件叠加
  等效标准。规划时发现 tpc 增量注入机制**只有"增加"路径成熟，"修改"路径是
  原始补丁**，标准演进中的"改"（如 C23 对 `int f()` 语义变化、K&R 定义废弃
  倾向）表达不了
- **现状盘点**：
  - ✅ **增加路径（inject_productions）成熟**：结构化树层操作（choice 候选插入
    + 全树 call 传播替换），幂等（祖先链判据防重复注入累积）、fail-fast
    （ADR-0003：目标缺失/解析失败直接报错）
  - ⚠️ **修改路径（inject_replace_rule）是原始补丁**：`prod.replace(old, new)`
    **字符串子串替换**，非树层结构化；**仅能改 production**（不能改 layout/
    analyzer/scope 等规则其他字段）；规则缺失只警告跳过（软，与 ADR-0003 相悖）；
    inject/replace 是两个分离机制，插件声明里没有统一的"我在以什么方式改目标"
    声明面
- **设计方向（未立项，仅研判）**：注入点统一声明"注入 or 改变"——`[inject]`
  段显式声明操作类型（如 `mode = "add" | "replace" | "remove"`），replace 升级为
  **树层结构化**（feature 树精确寻址替换/删除，非字符串子串），并统一 fail-fast。
  触发条件：C 标准插件族立项（届时"改"需求真实出现）或 verilog 插件出现同类
  需求时，从 ROADMAP 移回 TODO 立项

### 用户标定打包入口研判（2026-08-29，多语言分发前置）

- **触发**：语言包战略收敛为 verilog2005 + C23 后，"用户分发自己的语言包"
  （forkable 主张的兑现）成为自然延伸——用户把语法配置调试稳定、需求测试
  完成后编译打包。盘点发现现有打包管线**没有"用户标定"的声明面**
- **现状盘点（packaging/）**：
  - `facets.json`：**开发者硬编码**的四个预置切面（tpc-fmt/tpc-lint/tpc-check/
    tpc），切面 = 命令名集合（main.py `_register_subparsers(sub, allow)` 裁剪）
  - `build_pipeline.py`：读 facets.json → 生成入口脚本（entries/）→ Nuitka
    onefile（PE 署名 + SHA256）——**`_RULES_REL = "grammar/verilog"` 硬编码**，
    c4 打包不了、未来 C 语言包更不行
  - 结论：**Nuitka 编译是显式的，但"用户如何声明打包"这个需求侧面完全没体现**
- **设计方向（未立项）**：打包规格跟随语言包——`grammar/<lang>/tpc.toml`
  新增 `[packaging]` 段（target/description/facets），facets 缺省取该语言包
  `[commands]` 段已有的键（零重复）；build_pipeline 改为**扫描语言包声明**
  （`python packaging/build_pipeline.py` 无参 = 全部，`--lang <lang>` = 单个），
  `_RULES_REL` 硬编码消失，入口生成用该语言包 rules_dir（与调试时 main.py
  行为一致）。与插件聚类/渲染插件同哲学：一切可声明、可组合、用户标定
- **打包方式可选（2026-08-29 补充）**：语法包与二进制的结合方式由用户声明，
  不止"打进 exe"一种：
  - `bundle = "embedded"`——语法包数据打进 exe（现状 `--include-data-dir`，
    单文件分发，自包含）
  - `bundle = "external"`——语法包外置（exe 运行时按路径加载语法目录），
    引擎原生性能 + 语法可换——同一二进制服务多个语言包/版本，分发只发
    语法包数据；"调试期解释器热改 → 使用期二进制 + 外置语法"双态连贯
  - 两种形态语法都是**数据**（不是编译进代码），调试期热改能力不变；
    差异只在"语法随包携带 vs 外部加载"。用户可能有"语法打进二进制"的
    自包含分发需求（embedded），也可能有"引擎固定、语法可换"的
    多语言分发需求（external）——由 `[packaging] bundle` 标定
- **优先级**：低于 C 语言包——当前仅 verilog 一个语言包要打包，硬编码还能撑；
  触发条件 = C 核心基线立项（多语言共存）或出现"非 verilog 打包"需求

### 主流 lint 机制调研（2026-08-29，P1.10，规则库充实输入）

> 目的：调研市场主流 lint 工具的检查项清单 → 划"重合核心集合"（高频刚需）+
> "特化赛道"（差异化候选）→ 映射到 tpc 声明式规则模型。方法：三路并行
> （本地镜像直读 svlint/Veryl/flexlint + web 调研 Verilator/Verible +
> slang/Spyglass/HDL Checker）。原始抽取数据：`E:\research\svlint_rule_dump.txt`
> （155 条 name/hint/reason）、`E:\research\veryl_errors2.txt`（114 项）。

#### 第一路：svlint（159 条）+ Veryl check（114 项）+ flexlint（框架）

- **svlint 159 条**（155 syntaxrules + 4 textrules）——全部**单文件** AST 事件监听
  （NodeEvent Enter/Leave），无真正多文件符号表检查；仅 4 条 filename 匹配
  （`*_matches_filename`）与 1 条文件内状态（`default_nettype_wire_at_end`）
  需要文件级上下文。**"未使用/宽度/端口连接"svlint 完全没有**——这是 tpc
  语义层/handler 的差异化空间。主要类别：
  - 命名/标识符 ~80 条：`prefix_*`（input/output/inout/instance/module/package…）、
    camelcase、`re_forbidden_*`/`re_required_*`（26+26 对象，可配置正则，配 `.*`
    即整体禁用该特性）、`*_matches_filename`（4 条）
  - 端口/方向 6 条：`input_with_var`/`output_with_var`/`inout_with_tri`/
    `interface_port_with_modport`
  - 宽度/参数 7 条：`parameter_explicit_type`/`parameter_type_twostate`/
    `parameter_default_value`/`enum_with_type`/`unpacked_array` 等
  - 风格/空白 ~25 条：`style_keyword_*`（11 条空格规范）、`style_operator_*`（7 条）、
    `style_commaleading`/`style_indent`/`tab_character`/`style_trailingwhitespace`
    + 4 条 textrules（`style_textwidth`/`style_semicolon`/`style_directives`/
    `header_copyright`）
  - 结构/声明 15 条：ANSI 头强制、generate 关键字/标签、genvar 位置、
    `parameter_in_generate`/`parameter_in_package`、`loop_variable_declaration`、
    `multiline_if_begin`/`multiline_for_begin` 等
  - 时钟/进程 ~12 条：always_ff/latch/comb 的阻塞/非阻塞赋值禁令、
    `keyword_forbidden_always*`、`loop_statement_in_always_*`、
    `sequential_block_in_always_*`
  - 综合意图 11 条：`case_default`/`explicit_if_else`/`implicit_case_default`、
    `operator_case_equality`（`===` 不可综合）、`operator_incdec` 等
  - 指令/宏 2 条：`default_nettype_none`/`default_nettype_wire_at_end`
- **Veryl check 114 项**（13 条 Warning，其余 Error）——analyzer 两趟式
  （pass1 符号收集 → post_pass1 跨文件解析 → pass2 IR + 12 checker →
  post_pass2 unused/组合环）。**对 tpc 最相关的四类**：
  - 未使用类 3 项（W）：`unused_variable`/`unused_return`/`unassign_variable`——
    单文件但需两趟（符号+引用表）→ 对应 tpc"可注册检查 pass"语义层
  - 端口/实例化 10 项：`missing_port`/`unknown_port`/`unknown_param`/
    `missing_default_argument`——**跨文件**（端口表可跨文件）→ handler 兜底首选
  - 宽度/类型 16 项：`mismatch_assignment`（W）/`mismatch_type`/
    `mismatch_function_arg`——**跨文件**（类型可跨文件）
  - 赋值/控制流/时钟域：`multiple_assignment`/`combinational_loop`（SSA 数据流）/
    `uncovered_branch`（≈svlint case_default 语义版）/`missing_clock_signal` 等
- **flexlint**——无内置规则的纯正则 lint 框架（`.flexlint.toml` schema：
  pattern/required/forbidden/ignore/includes/excludes），**与 tpc `[[checks]]`
  pattern 层同构**。自带示例 4 条（if-with-begin/else-with-begin/always
  forbidden/if-with-brace）。**正则层能力 = tpc 声明式 pattern 覆盖上限参照**；
  正则不可表达 = case_default（需知道有无 default 臂）、always 族（需类型×
  运算符配对）、端口/模块结构、所有 Veryl 语义项（无符号表/作用域/类型概念）
- **交叉观察**：
  - 重合（高频刚需）：always 写法约束（三层各一）、分支完整性/锁存（case
    default/if-else/uncovered_branch）、可配置命名规则（re_*/prefix_*/camelcase）、
    inout 须 tri（svlint `inout_with_tri` = Veryl `missing_tri` 同一条）、宏卫生
  - svlint 独有：空格规范族（Veryl 有 formatter 故无）、ANSI 头强制、genvar
    位置、参数 2-state、filename 匹配
  - **跨文件差异化方向**（tpc handler 兜底）：符号解析（undefined/ambiguous/
    invisible）、实例化端口连接（missing/unknown port/param）、宽度/类型不匹配、
    未使用类、数据流类（combinational_loop/multiple_assignment）
- **对 tpc 的落点（三层分工）**：
  - pattern 层可全量覆盖：flexlint 全部 + svlint 文本类 + 正则命名族 +
    keyword_forbidden_* + 空白/排版
  - token 级（tpc linter 已有 token 流）：style_keyword_*/style_operator_*
    空格规范、multiline_*、eventlist_*
  - 语义层检查 pass（Veryl 模式）：宽度/未使用/端口连接/实例化——其中
    符号解析、端口连接、宽度匹配三类跨文件项需 **handler 脚本兜底**
  - 一句话：pattern 表达"长得对不对"，handler 表达"连得通不通、用没用、
    宽不宽"

> 待补：第二路（Verilator W 码 / Verible rule-sets）+ 第三路（slang/Spyglass/
> HDL Checker）完成后合并，再出"重合核心集合 + 特化赛道 + 映射评估"结论。

#### 第二路：Verilator W 码（136 个）+ Verible 规则（~60 条）

- **Verilator 现行 master 共 136 个警告码**（历史码已移除，非 200+）——预处理器 +
  elaboration + 数据流的**语义级 lint**，业界事实标准。类别精选：
  - 位宽/数值：WIDTH（汇总码 =WIDTHEXPAND+WIDTHTRUNC+WIDTHXZEXPAND）、
    WIDTHTRUNC（隐式截断）、WIDTHCONCAT、REALCVT、ENUMITEMWIDTH——语义层核心
  - 锁存：LATCH（组合 always 未全路径赋值→推断锁存）、NOLATCH、ALWCOMBORDER
  - 多驱动：MULTIDRIVEN（跨文件驱动源集合）、MULTIDRIVENPROC、BLKANDNBLK
    （混用阻塞/非阻塞）、ASSIGNIN（对 input 赋值）
  - 未优化/环：UNOPTFLAT（循环依赖禁优化）、DIDNOTCONVERGE（组合震荡）、IFDEPTH
  - 时序：TIMESCALEMOD（跨文件）、STMTDLY/ASSIGNDLY/COMBDLY、BLKSEQ
  - 常量：CMPCONST、UNSIGNED、INFINITELOOP、ZEROREPL
  - case：CASEINCOMPLETE（unique 枚举全覆盖语义）、CASEOVERLAP、CASEWITHX
  - **实例化/端口/层次（跨模块核心）**：PINMISSING、PINNOTFOUND、PORTSHORT、
    IMPLICIT（隐式声明）、MODDUP、MODMISSING、MULTITOP、DECLFILENAME、
    HIERPARAM——全设计 elaboration 后检查
  - 声明/生命周期：IMPLICITSTATIC、VARHIDDEN、SIMILARNAME、PARAMNODEFAULT
  - 流程语义：IGNOREDRETURN、NORETURN、SIDEEFFECT、PROCASSINIT、CONTASSINIT
  - 宏/预处理器：REDEFMACRO（跨文件宏表）、DEFOVERRIDE、PREPROCZERO、
    IMPORTSTAR、BSSPACE
  - 风格/文件：MISINDENT、EOFNEWLINE、GENUNNAMED、ASCRANGE、UNUSEDSIGNAL/
    UNUSEDPARAM/UNUSEDGENVAR
- **Verible 约 60 条规则**（43 条默认启用）——单文件、非预处理、纯语法/样式，
  **README 自述明确不做语义分析**（preprocessing/multi-file/AST 连通性不在其列）。
  机制分层：AST 级 ~48 / Token 级 5 / 行级 2 / 文本结构级 5。类别：
  - 组合/时序：always-comb（禁 always @*）、always-comb-blocking、
    always-ff-non-blocking、case-missing-default、module-begin-block
  - 命名风格（全部 RE2 正则参数化）：signal/enum/parameter/interface/macro/
    struct-union/constraint/dff/port-name 等 12 条
  - 文件组织：module-filename、package-filename、one-module-per-file、
    posix-eof（文件名级"伪跨文件"）
  - 排版：line-length、no-tabs、no-trailing-spaces
  - 实例化：module-port、module-parameter、forbid-defparam
  - 显式化：explicit-*-lifetime/type、typedef-enums/structs-unions、
    packed/unpacked-dimensions-range-ordering
  - 可读性：explicit-begin、mismatched-labels、suggest-parentheses、
    forbid-consecutive-null-statements
  - 验证环境：create-object-name-match、plusarg-assignment、
    invalid-system-task-function、uvm-macro-semicolon
- **交叉观察**：
  - 共有 10 组：BLKSEQ↔always-ff-non-blocking、DEFPARAM↔forbid-defparam、
    ENDLABEL↔mismatched-labels、EOFNEWLINE↔posix-eof、GENUNNAMED↔generate-label、
    CASEINCOMPLETE↔case-missing-default（Verilator 更强：含 unique 全覆盖语义）、
    DECLFILENAME↔module-filename、WIDTHTRUNC↔truncated-numeric-literal、
    VARHIDDEN↔instance-shadowing、MODDUP↔one-module-per-file
  - Verilator 独有 = 全部需 elaboration/数据流的语义类（WIDTH 家族/LATCH/
    MULTIDRIVEN/PIN*/UNOPTFLAT/UNUSED*）；Verible 独有 = 风格/命名/排版 +
    autofix/waiver 体系
  - **跨文件方向**：Verible 真跨文件 = 无（单文件设计），仅文件名级伪跨文件
    （module-filename 等 4 条）；跨文件检查（端口连接/模块解析/隐式声明/
    多驱动/宏重定义/timescale/未使用）**全落在 Verilator 侧**——tpc 语义层
    （analyzer 符号/类型/作用域）是差异化承接点
- **对 tpc 的映射**：
  - 语法层 ≈ Verible 全套风格规则 + Verilator 纯语法码（ENDLABEL/GENUNNAMED/
    EOFNEWLINE/ASCRANGE…）；Verible 机制分层可映射 tpc 语法层细分（行级→纯文本、
    Token 级→token 规则、AST 级→pattern 规则）
  - 语义层 ≈ Verilator 语义类（WIDTH/LATCH/MULTIDRIVEN/IMPLICIT/PIN*/UNUSED*）
    ——tpc 相对 Verible 的差异化空间，覆盖跨文件清单
  - 自定义层（handler）≈ UNOPTFLAT 环检测、DIDNOTCONVERGE、SVA NEVERMATCH、
    dff-name-style 流水线链检查
  - 工程借鉴：Verilator"汇总码"开关关系（WIDTH→3 子码）与默认开关分组、
    Verible ruleset（default/all/none）+ 参数化正则 + waiver/autofix 体系——
    适合 tpc 规则库 TOML 结构（默认开关字段、规则分组、pattern 参数化）

> 第三路（slang/Spyglass/HDL Checker）完成后合并，再出"重合核心集合 +
> 特化赛道 + 映射评估"结论。

#### 第三路：slang + Spyglass + HDL Checker

- **slang**（MikePopoloski，C++，全设计编译）——两级 lint：`slang` 驱动器警告系统
  （-W<name>/-Wno-<name>/-Wextra）+ slang-tidy（独立 linter，Checks:/CheckConfigs:
  配置，类 .clang-tidy，style-*/synthesis-* 两组）。子系统分族：
  - Analysis（lint 核心，编译+elaboration 全设计视角）：unused 族（net/variable/
    port/parameter/typedef/genvar/import…）、unused-but-set、undriven-net/port、
    inferred-latch/inferred-comb、shadow-*、missing-return、case 族（enum-dup-
    overlap-unreachable-incomplete…）、**net-inconsistent**（实例连接 vs 端口声明，
    跨文件）、multi-write/read-write、mixed-var-assigns/multiple-cont-assigns/
    multiple-always-assigns（多驱动）、missing-top（跨文件）
  - Declarations：**unconnected-input/output/inout-port**（实例 vs 模块定义，跨文件）、
    null-port、empty-connection、implicit-net、implicit-port-type-mismatch（跨文件）、
    unknown-library（跨文件）、**undefined-param-override**（跨文件）、
    static-init-*、unnamed-generate
  - Expressions：width-trunc/expand、**port-width-trunc/expand**（跨文件）、
    implicit-conv/sign-conversion、index-oob/range-oob/reversed-range、
    divide-by-zero、unsigned-arith-shift、优先级族（bitwise-rel-precedence、
    consecutive-comparison `x<y<z`）、unsized-concat
  - Lookup/Statements：**redefinition/duplicate-definition**（跨文件同名定义）、
    dup-import、**upward-name**（跨模块层次）、case-default、unused-result、
    empty-statement/dangling-else/misleading-indentation、nested-comment、
    newline-eof、redef-macro
  - slang-tidy：enforce-port-prefix/suffix（_i/_o/_io）、module-instantiation-
    prefix（i_）、only-ansi-port-decl、no-casex、no-defparam、no-legacy-generate、
    always-comb-nonblocking、generate-named；synthesis 组：no-latches-on-design、
    register-has-no-reset、always-ff-assignment-outside-conditional 等
- **Spyglass**（Synopsys，商业，业界 RTL lint"黄金标准"）——Rule→Goal→
  Sub-Methodology 三层（lint_rtl 默认 goal：连接性+仿真相关+不可综合+结构性；
  CDC/Constraints/DFT/Power/TXV 子方法论）；SGDC 约束 + waiver(.awl) +
  severity Fatal/Error/Warning/Info。类别：
  - 多驱动：W415（跨实例汇聚，ifdef 分支同时使能）
  - 锁存：W442aL（latch 推断）
  - **端口/网络连接（lint_rtl 核心，跨模块）**：W287a（实例输入未驱动）、
    UndrivenInTerm/UnloadedNet/UndrivenNUnloaded、W433（多 top）、
    W546（重复 design unit）、W701（include 未使用）
  - 位宽/算术：W164a/b（赋值截断/扩展）、W316/W376/W328、W313/W348（Verilint 兼容）
  - 综合质量：SYNTH_5159、W415a（if 分支双赋值）、W527（悬空 else）、
    W192/W193（空块）、W189/W208（translate_off 嵌套）
  - 时钟（lint 内建）：Clock_sync05/06（多时钟域采样/组合）、setup_quasi_static
  - **CDC（独立方法论，高成本）**：AC_unsync/sync/conv/glitch/cdc/datahold/fifo、
    Ar_unsync/sync/asyncdeassert（复位域）、Reset_sync——依赖时钟域划分+同步
    结构识别+跨域路径分析，结果靠 SGDC 约束压误报
- **HDL Checker**（suoto，Python，227★）——**LSP 包装器**，委托 GHDL/ModelSim/
  Vivado 做检查，自带少量正则静态检查 + 自研 design-unit 解析器。价值点：
  - 内建检查：Unused signal/constant/generic（**词频式判定有误报，README 自述
    caveat——tpc 用真符号表应做精确引用计数，避坑**）、Comment tags
    （TODO/FIXME/XXX，token 级零成本）
  - **跨文件资产（tpc 最值得借鉴）**：design-unit 提取（module/entity/package
    注册）、依赖图与编译顺序（include/import/class → 拓扑排序）、库归属推断
  - 确认差异化：hdl_checker **不自己做端口连接/实例化正确性检查**——正是 tpc
    可做深的地方
- **交叉观察（三路合并）**：
  - 高频刚需（第一优先级，语义层符号表可表达）：未使用声明/端口/参数（slang
    unused-* / Spyglass 未驱动 / HDL Checker Unused）、位宽不匹配（width-trunc/
    W164）、多驱动（multiple-always/W415）、锁存推断（inferred-latch/W442）、
    case 完整性（case-*/W527）、隐式声明（implicit-net）、注释标签
    （TODO/FIXME，零成本）
  - 跨文件差异化（需多文件输入，handler 兜底）：端口连接（slang unconnected-
    port / Spyglass W287a）、连接位宽（port-width-*/W164）、实例输入未驱动
    （W287a）、参数覆盖不存在（undefined-param-override）、符号解析
    （unknown-library/W546/W433/redefinition）、include 未使用（W701）
  - CDC/时序（远期高成本，机制可挂但需独立图分析 + SGDC 式约束）：
    AC_/Ar_/Clock_ 族——slang 不做时钟域建模，印证 CDC 是独立高成本层；
    建议先做"同步器/时钟端口命名"可正则化约定（低成本实际价值），全量复刻进远期
- **实现路径提示（跨文件检查两步走）**：① design-unit 注册表 + 依赖排序
  （参照 HDL Checker database/parsers 思路，引擎基建）；② 端口连接/实例化/
  符号解析规则（kind 分发 + handler 兜底，handler 拿两文件符号表对比）。
  规则 TOML 可加 `group`（syntax/semantic/custom）与 `severity` 字段
  （对齐 slang 子系统分组 + Spyglass Rule→Goal 分级思想）。
  **2026-08-29 升级命名**：① 即"**elaboration 底座**"（ROADMAP P2.7）——
  Verilator/slang/Spyglass 的跨文件检查全是 elaboration 后视角；tpc 现有
  第一层雏形（module_index + inst_sites + inst_check），缺连接关系展开/
  驱动负载图/层次展开三层。无此底座，未使用/多驱动/端口完整性/位宽匹配
  全做不了。

#### 重合核心集合 + 特化赛道 + 映射评估（P1.10 结论）

- **重合核心集合（高频刚需，多工具共有，第一优先级）**：
  1. 命名/风格族（svlint prefix_*/camelcase ↔ Verible 12 命名规则 ↔ Veryl
     invalid_identifier ↔ slang-tidy port-prefix）——tpc NC 族已覆盖大半，
     补 port 前缀/实例前缀可配置化
  2. 未使用类（Veryl unused_variable ↔ Verilator UNUSEDSIGNAL ↔ slang unused-*
     ↔ HDL Checker Unused）——语义层符号表，tpc 最高价值增量
  3. 位宽不匹配（Verilator WIDTH ↔ slang width-trunc ↔ Spyglass W164）——
     语义层类型宽度，增量大但需宽度传播
  4. 锁存推断（Verilator LATCH ↔ slang inferred-latch ↔ Spyglass W442 ↔
     svlint case_default/explicit_if_else）——语义层控制流
  5. case 完整性（svlint case_default ↔ Verible case-missing-default ↔
     Verilator CASEINCOMPLETE ↔ slang case-* ↔ Spyglass W527）
  6. always 写法（svlint keyword_forbidden_always ↔ Verible always-comb ↔
     Verilator BLKSEQ ↔ slang always-ff-blocking）——语法层可做
  7. 端口命名/方向（svlint prefix_input/output ↔ Verible port-name-suffix ↔
     Veryl invalid_direction ↔ slang-tidy port-prefix）——语法层
  8. 实例化端口连接（Veryl missing_port/unknown_port ↔ Verilator PINMISSING/
     PINNOTFOUND ↔ slang unconnected-port ↔ Spyglass W287a）——**跨文件，
     handler 兜底，tpc 差异化**
  9. 多驱动（Verilator MULTIDRIVEN ↔ slang multiple-always ↔ Spyglass W415）——
     跨进程驱动分析，语义层
  10. 宏/指令卫生（svlint default_nettype ↔ Verilator REDEFMACRO ↔ slang
      redef-macro ↔ Spyglass W701）——跨文件宏表
- **特化赛道（单工具独有，选择性吸取）**：
  - Verible 独有：autofix/waiver 体系、line-length/no-tabs 排版族、typedef-
    enums/structs-unions、packed/unpacked 维序——**排版族零成本入语法层**
  - svlint 独有：空格规范族（style_keyword_*/style_operator_*）、ANSI 头强制、
    genvar 位置、参数 2-state——**语法层零成本**
  - Verilator 独有：UNOPTFLAT 环检测、DIDNOTCONVERGE、SVA NEVERMATCH、
    CMPCONST/UNSIGNED 常量分析——自定义层（handler），中成本
  - Spyglass 独有：CDC 方法论（AC_/Ar_/Clock_ 族）——远期高成本，先做可正则化
    的同步器/时钟命名约定
  - HDL Checker 独有：design-unit 注册表 + 依赖排序思路——**跨文件引擎基建，
     直接借鉴**
- **映射评估（→ tpc 规则模型）**：
  - 语法层 pattern 可全量覆盖：命名族（NC 扩展）、排版族、keyword 禁用、
    always 写法、宏卫生——**零 handler，纯声明式，成本低**
  - 语义层检查 pass（analyzer 符号表/类型/驱动分析）：未使用类、锁存推断、
    多驱动、位宽（需宽度传播）——**中成本，需 analyzer 扩展**
  - 自定义层 handler 兜底（跨文件）：端口连接、实例化、符号解析——**差异化
    核心，需 design-unit 注册表 + 依赖排序基建（HDL Checker 思路）**
  - 规则 TOML 结构建议：加 `group`（syntax/semantic/custom）字段 + 默认开关
    （对齐 Verible ruleset / Verilator 汇总码开关）
- **1-2 条差异化自定义规则立项候选（跨文件类为核心样例）**：
  1. **实例化端口连接检查**（候选）：实例连接端口 vs 模块定义端口——不匹配/
    缺失/多余，跨文件 handler 兜底（对标 Veryl missing_port/unknown_port +
    Verilator PINMISSING/PINNOTFOUND + Spyglass W287a）
  2. **未使用声明检查**（候选）：wire/reg/parameter 声明后未使用——语义层
    符号表引用计数（对标 Veryl unused_variable + Verilator UNUSEDSIGNAL +
    HDL Checker Unused，用真符号表避免词频误报）
  3. 或 **未驱动/未连接端口**（对标 Spyglass UndrivenInTerm + slang undriven-
    port）——跨文件，与候选 1 可合并为"端口完整性"族

#### 规则实现进度（2026-08-29，P1.10 落地）

- **elaboration 底座**（ADR-0008，提交 3acae77）：层 2 `_elaborate_connections`
  （实例化点端口连接展开，Named/Ordered 双形态）+ 层 3 `_build_signal_graph`
  （全工程信号驱动/负载图，output=input 方向由语言包 `output_dirs`/
  `input_dirs`/`inout_dirs` 声明），注入 `context.extra`（connections/
  signal_graph/方向集）。
- **UN001 未使用声明**（a22f081，unused_check 插件）：语义层符号表引用计数
  ——遍历 AST 收集 `_symbol_ref`，声明后零引用的 wire/reg/integer 报未使用。
  排除声明标识符（`_collect_self_decl_ids` 处理 `wire a, b;` 共享声明节点）/
  端口（接口非内部信号）/`_` 前缀豁免；**parameter/localparam 豁免**（接口
  预留/条件编译常见，对标 Verilator UNUSEDPARAM 默认关闭）。analyzer 存
  `_ast` 供 postpass 遍历。
- **W104 未连接端口**（57d6e83，inst_check 扩展）：跨文件端口完整性——
  elaboration 层 2 连接展开 + 模块端口方向判定，input/output 端口实例化
  未连接报 W104（inout 悬空豁免，三态可能有意）。对标 Veryl missing_port/
  Verilator PINMISSING。
- **W105 多驱动**（394ec51，inst_check 扩展）：elaboration 层 3 信号图
  drivers≥2 报多驱动（error 级）；本文件信号去重防跨文件重复报。对标
  Verilator MULTIDRIVEN / Spyglass W415。
- **CC001 case 完整性**（1f94fbc，case_check 插件）：case 无 default 分支
  报警告（组合逻辑未覆盖全分支 → 锁存/仿真综合不一致风险）；嵌套 case/
  casex/casez 全覆盖。对标 svlint case_default / Verible case-missing-
  default / Verilator CASEINCOMPLETE / slang case-* / Spyglass W527。
  Verilog-2005 无 unique/priority 限定，不处理 unique 豁免。
- **W106 inout 须 tri**（5067e8b，inst_check 扩展）：inout 端口数据类型须
  tri（三态总线语义）；端口 net_type 提取（结构协议 port_type 字段 +
  ModulePort.net_type）+ 遍历本文件 AST 的 inout 声明（避免跨文件重复报）。
  对标 svlint inout_with_tri = Veryl missing_tri（完全重合）。
- **LC001 锁存风险**（d5148d3，latch_check 插件）：组合 always（@* 或电平
  敏感，无 posedge/negedge）内 if 无 else → 锁存风险（条件不满足时信号
  保持，仿真/综合不一致）。时序 always 内 if 无 else 是合法复位写法
  （`if (!rst_n) q <= 0;`），豁免。有限版：只查"if 无 else"可静态判定
  形态，不做完整控制流路径分析。对标 svlint explicit_if_else /
  Verilator LATCH / Veryl uncovered_branch / slang inferred-latch。
- **评估不做**：always 写法类（裸 always 无事件控制）——仿真代码大量合法
  使用（`always begin` 无限循环），误报高，不做（对标 svlint
  keyword_forbidden_always 需 always_comb 语义，Verilog-2005 无）。
- **NC012/NC013 命名补全**（随 a22f081）：integer/type 符号命名规则（NC 族
  原缺这两个 kind）。
- **三层捕获能力验证**：语法声明式（NC 族）/ 语义符号表（UN001）/ 跨文件
  handler（W104）各有一个真实规则，三层机制全被真实规则消费过。

#### 试水检出准确度评测（2026-08-29，0.1.1 试水第一弹）

试水 = 构建测试检验规则检出准确性。新评测体系（与既有 linter 评测
eval_lint_accuracy.py 并列，analyzer 层）：

- **标注样本集** `tests/e2e/samples/check_accuracy/`：26 case（15 正样例 +
  11 负样例），覆盖 7 类核心规则 + 边界变体（共享声明 `wire a, b;` 只报
  未用者 / casez / 电平敏感 always / 双实例 output 汇聚）+ **复合小工程**
  `project_bus_ctrl`（3 文件，同含未使用信号 + 缺连端口 + 多驱动 +
  case 无 default 4 类缺陷，验证真实工程形态的跨文件检出）。
- **评测脚本** `tests/e2e/eval_check_accuracy.py`：逐 case 跑 ProjectChecker，
  按"期望码集合 ⊆ 实际码集合"判定（pos：漏检 = MISS / 期望外 = FP；
  neg：focus 内任意检出 = FP），输出 recall/FP/precision + 逐规则明细。
- **pytest 门禁** `tests/e2e/test_check_accuracy.py`：断言 recall=100% +
  FP=0 + 样本全可解析（与 --json 输出单一来源判定）。

首测基线（80% recall / 3 FP）暴露 3 个真实缺陷，修复后 100% / 0 FP：

1. **W105 全漏检——assign 驱动缺位**（信号图只收实例 output 连接，连续
   赋值 LHS 不进 drivers）。修复：引擎 `_build_signal_graph` 按协议
   （`assign_rule`/`assign_target`/`assign_extras`/`assign_extra_target`，
   语言知识仍全在配置）收集 assign 驱动（"file:assign#N" 按语句编号，
   同信号两条 assign 不因文件级去重漏报）；插件 `_check_multi_driver`
   归属判定扩展（本文件 assign 目标优先定位）。插件侧取目标信号名用
   `_sig_text`（穿透 PrimaryExpr 合成包装取首段 content + 信号名形态
   过滤，与引擎 renderer 渲染同语义——`_text` 对合成节点返回空是本轮
   首个调试发现）。
2. **`inout tri` 语法缺口**（PARSE-ERR）：`TypeSpecNoReg` net 类型位只有
   `keyword.wire`，`inout tri a` 无法解析（12 种 net 类型中仅 wire 进主
   包）。修复：主包 token 声明加 `tri`（三态总线可综合，与 wire 同待遇；
   nettypes 插件 token 重复声明合并无害）+ `TypeSpecNoReg`/`TypeSpec`
   net 位加 `keyword.tri`。**连带暴露既有测试盲区**：test_inout_tri_clean
   用 `inout tri [7:0] d`——解析失败 → 语义跳过 → 断言"无 W106"假通过。
   评测集的 parse_fail 检测把这类假阳性显形。
3. **命名规则不豁免 `_` 前缀**（负样例 `wire _dummy;` 报 NC003）：`_` 前缀
   是 Verilog 社区"故意不用/占位"约定（UN001 已豁免），命名约定应一致。
   修复：naming.toml 全部 pattern 前缀加 `_?`（数据层改动，零引擎知识）。

试水结论：评测体系把"规则能检出"从单元测试的孤例证明升级为**带标注的
正/负样例集合证明**，且样本构造时对"命名合规/文件一致"等旁路规则的要求
本身就是规则的交叉验证。当前 7 类核心规则（18 期望码）100% recall +
0 FP（26 case 全绿）。

#### elaboration 层 3 热点：_module_of 全树扫描 → per-file 映射（2026-08-31）

背景：用户问 elaboration 是否值得 Rust/PyO3 下沉——先 profile 定位
（picorv32 单次 check，cProfile）：`_build_signal_graph`（elaboration
层 3）cumtime 8.33s / 21.6s ≈ **39% 第一大热点**，其中 `_module_of`
仅 76 次调用就 7.5s——每次对**新节点**都遍历全 AST 的 ModuleDecl +
`_subtree_contains` 子树包含判定 = O(N×树) 平方级（251 万次
`iter_children`）。

修复（analyzer/checker.py）：`_module_of` 改 per-file 预计算
`{id(节点): 模块名}`（`_precompute_module_map`，一次 DFS O(树)、查询
O(1)）——与 `_in_active_generate` 同款手法（2026-08-29 先例 103s→
秒级）。`_subtree_contains` 的 generate 求值调用保留（那些是局部子树
判定，非全树扫描）。

实测（同一环境）：**21.6s → 14.1s（-35%）**，`_build_signal_graph`
掉出热点前 12；剩余热点 = parser 5.1s（~36%）+ iter_children 3.8s +
_analyze 3.6s。全量 1467 passed + 8 skipped、hardcode gate PASS、
benchmark 对拍数字与基线逐项一致（共识 44/抑制 34/范围外 156）——
语义零回归。

结论（回答"elaboration 是否上 Rust"）：**elaboration 慢是算法缺陷
（O(N×树) 平方级），不是 Python 慢**——Python 层预计算即 -35%，零
风险。Rust/PyO3 下沉（P3.5 已立项）的正确对象是**剩余真热点**：
parser 骨架（~36%）与 iter_children 遍历本身——且 P3.5 前置 P3.1
span 绑定（解析器接口稳定后下沉才不白做）。elaboration 层 3 在
模块映射预计算后已是 O(树) 常数级，不再值得桥接。

#### 实例树深度实测：verilog-ethernet（2026-08-31，P2.7 全量规模评估）

动机：上一节结论"elaboration 层 3 已是 O(树) 常数级、不值得 Rust"的
前提是全量实例树展开（P2.7 层 3 扩展）的增量规模未知——用户点名
Verilog 以太网协议栈（Alex Forencich verilog-ethernet，3.1k stars，
rtl/ 98 核心模块：udp/ip/arp/eth_mac/eth_phy 分层 + example/ 25 个
FPGA 顶层），实测其实例树深度，回答"补齐 P2.7 后 elaboration 占比
会到多少"。

实测（全文件 parse，287 文件：rtl + example 全部）：
- 模块定义 114（7 文件解析失败：6 个参数化宏生成模块 arp_eth_rx 等 +
  fpga.v 顶层 Xilinx 原语 PLL_BASE 截断——tpc 的 Verilog-2005 子集边界）
- 未定义目标全为**库模块**（Xilinx 原语 BUFG/IDDR/ODDR + axis_fifo/
  arbiter/sync_reset 等 lib/ 组件）——属正常，实例树统计不受影响
- **实例树最大深度 7**（fpga → fpga_core → eth_mac_1g_gmii_fifo →
  eth_mac_1g_gmii → gmii_phy_if → ssio_sdr_out → oddr → altddio_out）
- 典型协议栈链深度 6-7（fpga → fpga_core → udp_complete_64 →
  ip_complete_64 → arp → arp_cache → lfsr）
- 模块直接实例数分布：{0:45, 1:19, 2:16, 3:15, 5:7, 6:4, 7:1, 8:2,
  22:1, 64:1, 73:1, 189:1, 415:1}——**尾部大扇出**（22/64/73/189/415
  实例的模块，如 eth_mac_quad_wrapper 等 wrapper/quad 级），扇出比
  深度更显著

结论（回答"全量 elaboration 占比"）：
- **深度 7 是真实上限量级**——比当前语料（1-2 层）深 3-4 倍，但
  仍是常数级小深度（Verilog 层次天然有限，协议栈/SoC 一般不超 8-10
  层）；**真正的规模因子是扇出**（415 实例的 quad wrapper）——全量
  实例树节点数 ≈ Σ(每层扇出) 可达数千，elaboration 成本从 O(单层
  连接) 变为 O(实例树节点 × 端口连接)。按此估算全量后
  `_build_signal_graph` ~2-5s（当前 0.96s 的 2-5×），占总时间
  12-25%——**仍是次要热点，但不再是"不值得优化"的量级**；且深度
  展开的增量主要在"信号沿端口穿透"而非"建图本身"。
- **对 P2.7 的意义**：层 3 扩展（实例树层次展开）的真实收益 = 深层
  多驱动/未驱动判定（如 quad wrapper 内多层信号汇聚），verilog-
  ethernet 的 7 层 + 415 扇出是**合格的压力测试语料**——比现有 7
  工程（最深 1-2 层）更能暴露 elaboration 深层缺口，可纳入 benchmark
  语料候选（需先解决 fpga.v 的 Xilinx 原语解析边界 + lib/ 依赖）。
- **对 P3.5 的意义**：elaboration 全量后 ~2-5s 中，"信号沿端口穿透"
  是纯数据流遍历（Python dict/list 操作），桥接 Rust 的收益比 parser
  骨架小（无语法回朔）；维持结论——Rust 对象仍是 parser，elaboration
  优先吃算法层（预计算已吃 -35%，深度展开时再 profile）。

#### 实例树层次展开：驱动穿透实现（2026-08-31，P2.7 层 3 扩展闭环）

- 定位：P2.7 层 3 扩展——信号图从"实例→信号"单层升级为"驱动源穿透
  到被实例化模块内部真实驱动源"（对齐 Verilator elaboration 后视角：
  MULTIDRIVEN 按实际驱动者判，非按实例原子判）。
- **实现（analyzer/checker.py）**：
  - `_build_module_insts()`：per-module 实例表（{模块: [(实例名, 目标
    模块, PortConnection)]}，从层 2 connections 按 _module_of 归组）
  - `_port_sources()`：模块内端口驱动源（**限定 ModuleInfo.node 子树**
    ——探针暴露同文件多模块同名 assign 污染；裸源 = assign#N / proc /
    inst:{实例}:{子端口}，缓存跨实例化点复用）
  - `_resolve_port_drivers()`：递归穿透拼实例路径（inst 子引用下钻）；
    返回 (源列表, 模块是否定义) 区分**悬空**（定义但无驱动 → 不记，
    对齐 Verilator）与**黑盒**（未定义 → 原子实例源兜底，保守）
  - `_build_signal_graph` 消费：output 连接驱动源 = 穿透结果（带路径），
    inout 双向不变，input 负载不变
- **验证**：3 层探针（top→mid→leaf）穿透路径正确（`u_mid/u_leaf:
  assign#1`）、悬空 output 不记驱动（修复了原子源误报 W105）、单链
  不误报；测试 +1（test_dangling_output_not_driver）、3 个既有断言
  更新（驱动源从原子 `u1` 变 `u1:assign#N` 穿透路径）；全量 1468
  passed；benchmark 真实语料 7 工程对拍数字与基线逐项一致（共识 44/
  抑制 34/范围外 156）——穿透零新增误报/漏报。
- **verilog-ethernet 实测**：udp_complete 入口 17 模块 1291 信号图键、
  **123 条穿透驱动源**（两层路径 ip_inst/ip_eth_rx_inst:assign#29）；
  W105 9 条全在 axis_fifo 内部 generate 互斥分支（OUTPUT_FIFO_ENABLE
  求值缺口）——**stash 对拍确认穿透前即存在**，随即修复（见下"generate
  `!参数` 条件求值"）。
- **边界**：位置连接（ordered）output 驱动仍保守记负载（方向未知）；
  参数覆盖沿穿透链的宽度求值未做（端口宽度含参数时穿透源照记，宽度
  判定归 width_check B3/B4）——均为"需要时再做"。

#### generate `!参数` 条件求值补全（2026-08-31，W105 误报 9→0）

- 定位：verilog-ethernet axis_fifo `generate if (!OUTPUT_FIFO_ENABLE)
  ... else begin : output_fifo` 形态 9 条 W105 误报（Verilator 0 报
  MULTIDRIVEN）。根因：`_eval_gen_cond` 对 `!参数` 返回 None（含标识符
  的表达式不匹配纯数字正则 → 不可判）→ `expand_if` 整块按当前活性
  展开 → 双分支全 active → else 分支 assign 被误计驱动源。
- **修复（analyzer/checker.py）**：`_eval_gen_cond` 增 `!参数名` 分支
  （`re.fullmatch(r"!\s*([A-Za-z_]\w*)")` → 参数值数字 → `int(v)==0`）。
  顺带清理 `_branch_active` 重复定义（L1061 死代码，被 L1085 覆盖）。
- **验证**：verilog-ethernet 9 条 W105 → **0**；回归测试 +2
  （`!EN` else 不报 / `!EN` 选中分支内真双驱动仍报）；真实语料对拍
  数字与基线逐项一致（共识 44 含 picorv32 W105 8 条不变——修复
  精确零误伤）；全量 1468 → 1470 passed（+2）。
- **边界**：`!参数` 只处理纯数字参数值；`!参数` 值含表达式（如
  `!WIDTH/2`）仍不可判 → 保守全 active（不误伤真多驱动）。

#### parser packrat 记忆化尝试（2026-08-29，已回退）

背景：渲染器记忆化后（见 ROADMAP P2.3 更新），parser 是单遍管线最大热点
（~50%）。尝试给 production 匹配加失败记忆化（对标 linter 先例 bf8f782/
db14e70）——**只缓存失败**（成功有节点构造/指针推进副作用不缓存；
FOLLOW/exclude 在调用方不在本层，天然不入缓存）。93 文件对拍（真实语料
9 + normal 32 + errors 3 + 评测样本 + macro）发现 1 处差异：**picorv32
输出 36B 差异**（`$signed({...})` 拼接处 flat/broken 布局选择不同）。

根因：`rule_frame`（parser/_production.py:169）的 `sibling_counter`
（语义路径自然序，AST 节点 path 属性 `{rule}[{sn}]`）在**失败尝试时也
递增**。失败缓存命中跳过"失败规则内部子规则的尝试"——内部子规则的
sibling_counter 递增被跳过 → 后续成功规则的 path 编号变化 → 渲染对齐/
Union 布局预算不同 → 输出差异。失败尝试的内部递归副作用（子规则计数）
**无法在不执行的情况下重放**（执行 = 不缓存），等价记忆化在此设计下不可行。

结论（诚实边界）：失败记忆化与 sibling_counter 的"失败也计数"语义冲突。
彻底解决需重构 path 计数语义（只在成功时计数——改变现有输出，全量保真
回归风险大），或改缓存粒度到无副作用层（原子 token 匹配，收益有限）。
按"行为差异即回退"约定，改动已还原（git checkout），parser 保持无记忆化。
后续若做，需先定 path 编号语义变更的接受度。

#### 编译版（Nuitka onefile）管线速度实测（2026-08-29）

动机：picorv32（3049 行）解释版 format 4-5s，问编译版量级。环境：Nuitka
4.1.2 + MinGW，`packaging/build_pipeline.py tpc` 全切面 onefile（8.5MB）。

实测（同一当前代码，picorv32 format，预热后）：
- **总量**：exe 5.06s vs 解释 4.49s——**编译版反而慢 ~12%**
- **净计算**（扣启动）：exe 启动固定 0.81s（onefile 解包 + Nuitka 运行时，
  解释版 0.10s）→ format 净 4.25s vs 4.39s、check 净 1.27s vs 1.34s——
  **编译净收益仅 3-5%，可忽略**
- 输出逐字节一致（131143B）

机制：解析/渲染是 match/case 结构模式匹配 + 动态分发 + 数据驱动（TOML
配置加载、节点属性访问）为主——Nuitka 编译成 C 后这些结构无数量级收益；
onefile 解包启动固定开销 ~0.7s 吃掉全部编译收益。

结论（诚实）：**编译版价值在分发（无 Python 环境部署），不在速度**。速度
优化应继续走算法层（渲染器记忆化已做；parser 需先重构 path 计数语义）。
若未来要编译版速度，方向是减小启动面（onedir 模式省解包）+ 热循环改
C 扩展/原生，均另案。

附带修复（同次构建暴露）：打包漏插件 postpass .py——checks/ 聚类后新
插件的 `_*.py` 经 load_postpasses 动态 import，Nuitka 静态收集看不到、
include-data-dir 不保证携带 .py → exe 启动即崩（ValueError postpass 模块
不存在）。build_pipeline 显式 `--include-data-files` 逐个携带插件 .py +
构建后 smoke test（format/lint/check 各跑样本，任一失败即构建失败）——
防静默坏包（0.1.0 exe 能跑只因当时无 checks 插件）。

#### PyPy JIT 实测（2026-08-29，结论：不切换）

动机：理论分析 PyPy 的 JIT（去虚拟化/内联/逃逸分析）应命中 tpc 的"对象图
遍历 + 动态分派"负载（解析器/语义分析），预期 2-4x。环境：PyPy 7.3.20
（Python 3.11.13，winget 安装，tomllib 可用）。

实测（同一当前代码）：
- **长任务**（5 万行合成工程 check，316,891 tokens）：PyPy **36.2s** vs
  CPython 45.3s——**快 22%**（8.8k vs 7.0k tok/s；两遍稳定，JIT 预热后）
- **短任务**（真实语料 9 文件 format，每文件独立进程）：PyPy 3.3k tok/s vs
  CPython 5.4k tok/s——**慢 38%**（JIT 预热 + PyPy 启动开销 > 短任务本身）

机制：长任务 JIT 预热后仅 +22%（低于理论 2-4x——match/case 结构匹配在
PyPy 的 JIT 收益有限、字典/字符串部分无收益拖累整体）；短任务每次进程
冷启动 + 预热期收不回成本 → 净损失。

结论（诚实）：**PyPy 不适合 tpc 的实际使用形态**（单文件 CLI 命令为主、
短任务占多数）；22% 的长任务收益不值得引入版本滞后（3.11 线）与生态
风险。**CPython 保持现状，算法层仍是提速主线**（渲染缓存 -57% 实证；
parser 记忆化待 path 语义重构）。附带数据：真实语料 9 文件 = 100k token，
check 吞吐 7k tok/s（5 万行 ≈ 45s），format 热吞吐 5.4k tok/s。

#### 位宽一致性落档（2026-08-29，A/B/C1 闭环）

实现位置 = 语义插件 `grammar/verilog/plugins/checks/width_check/`
（求值器+推断器+规则全在插件层，引擎零改动——"语言知识不进代码"的
又一次验证；6 提交 1c04652..7b4f167 + C1 提交）。

- **A 常量宽度域**：A1 符号宽度表（类型级/声明符级/多声明符按名对齐，
  integer 固定 32；body 端口宽度走类型声明符号——方向=属性、类型=符号
  设计）；A2 常量求值器（`eval_width_text`/`eval_const_expr` 手写递归
  下降防 RCE/`literal_width`）；A3 表达式宽度推断（原子/拼接/复制/位选/
  一元/二元按 op 分派/三目/$signed 同宽，未知保守 None）；A4 **W201**
  赋值截断（assign/阻塞/非阻塞/多目标，扩展与未知不报）；A5 评测扩充。
- **B 参数化宽度**：B1 模块参数默认值表；B2 符号化常量求值
  （`eval_expr_params` 链式参数 `W=DATA_W/2` 递归）；B3 跨模块参数传播
  （实例化覆盖 `#(.P(v))` 覆盖后参数表三层合并：调用者参数→模块默认→
  site 覆盖；端口连接截断复用 W201；命名连接覆盖，ordered 留后续）。
- **C1 SELRANGE**：**W202** 位选/下标/切片越界（error 级；常量索引才判，
  变量索引保守跳过；参数化 base 求值后判定）。
- **C2/C3 评估不做**：C2 自赋值宽度变化与 W201 重叠（截断已报），且
  `a=a+1` 累加器合法用法普遍（Verilator 对 unsized 常数自赋值也不报）；
  C3 unsized 精化（自定尺寸语义）是 Verilator 最复杂部分，按 32 位默认
  会误报合法累加器——当前保守实现（unsized→None 不报）是合理基线，
  $signed/$unsigned 已在 A3 支持（同宽）。
- **节点形态知识**（B/C 调试积累）：token 文本在 value 属性；pratt 合成
  BinaryOp(op 为 str)；`ReplicateExpr.value` 业务属性勿当 token；
  `SelectSuffix.range_suffix` 实测 list（非 seq 节点）。
- **验证**：38 测试全绿；评测 34 case（20 pos + 14 neg）23 期望码 100%
  recall / 0 FP；全量 1418 passed + 8 skipped；真实语料（picorv32/
  darkriscv/tv80/uart/ice40）W201+W202 均 0 误报——保守策略（sized 域 +
  未知跳过）在真实代码上零误伤。

#### 参数覆盖后模块内位宽截断：漏检边界 → 已修（2026-08-31，W201 B4）

用户场景：模块 A 内**固定位宽**变量 ← **参数位宽**变量赋值，外层实例化
覆盖参数——异常截断只在覆盖后出现，默认参数下不截断：

```verilog
module A;
  parameter W = 4;              // 默认下 x 4 位 == y 4 位，不截断
  reg [3:0] y;
  wire [W-1:0] x;
  assign y = x;                 // 外层覆盖 W=16 后：16→4 截断
endmodule
module B;
  A #(.W(16)) u_a();            // 覆盖点
endmodule
```

- **修复前实测**：tpc 不报（漏检）；Verilator 5.050 `%Warning-WIDTHTRUNC
  ... In instance 'B.u_a' ... generates 16 bits` 能报（elaboration 每
  实例化点独立展开）。
- **根因（源码级）**：模块内赋值检查 `_check_assignment_widths` 的参数
  表 = `_file_params`（B1 模块**默认**参数值）——B3 的实例化覆盖合并
  （`_override_params`）**只在实例化点端口连接宽度检查用**（
  `_check_port_connections`），不回传被实例化模块**内部**的赋值。
- **修复（B4）**：`_check_inst_internal_widths`——对有**有效覆盖**
  （覆盖值 ≠ 模块默认值）的实例化点，用覆盖后参数表重算目标模块
  内部赋值截断（W201，主 node = 实例化点、related 跨文件定位模块内
  赋值处）。符号宽度表从 `ModuleInfo.node` 走查（跨文件目标模块无
  analyzer 符号表；复用 A1 提取判据）；**不设 `_hier` 回调**（跨文件
  层次引用宽度留给 hier 插件，此处保守 None 防误判）；预筛"模块内部
  存在参数化宽度"才重算（固定宽度模块覆盖参数不影响内部赋值，单元库
  空壳模块跳过省遍历）。
- **边界处置**：无覆盖/覆盖值==默认值 → 跳过（模块定义处 A4 默认参数
  检查已覆盖，防重复报）；扩展方向（RHS<LHS）不报（与 A4 同策略）；
  覆盖值引用调用者参数（`#(.W(SIZE))`）→ 三层合并已支持。
- **验证**：7 组探针（默认截断/覆盖后截断/覆盖同值/无覆盖/多实例化
  一宽一窄/端口参数化扩展/固定宽度模块）全符合预期；跨文件场景
  （A 独立文件 + B 实例化）related 正确指向 a_mod.v；评测集 +2 case
  （正 W201_param_override_trunc / 负 W201_param_override_clean）门禁
  通过；真实语料对拍（7 工程）B4 零新增诊断、全量 1467 passed + 8
  skipped、hardcode gate PASS——改动集中在 width_check 插件，引擎零
  改动（"语言知识不进代码"又一次验证）。

#### 试水第二弹：真实开源工程误报率评测（2026-08-29）

动机：0.1.1 暴露前的最后拼图——拿真实开源工程（9 语料：darkriscv/
picorv32/serv/tv80/UART×3/simcells/ice40，合法代码）跑**完整检查集**，
量真实误报率并修复。

**前置修复**：`tpc check` 不支持宏展开（真实工程全含 `ifdef` → parse
失败不可用）——ProjectChecker 加 expand_macros（scan_directives +
expand_tokens，默认开，无宏文件零影响；诊断行号基于展开后文本，宏 span
反向映射属 P3.3）。

**修复前诊断面 → 修复后**（修复 4 缺陷，提交 c3bde36）：

| 规则 | 修复前 | 修复后 | 根因与修复 |
|---|---|---|---|
| W105 | 41 | **10** | 信号图键改 (模块, 信号)——ice40 SB_LUT4/ICESTORM_LC/SB_MAC16 各有端口 O 被合并 |
| W201 | 93 | **31** | 存储器 word 选择误判 1 位（数组符号表）+ 自引用位选豁免（active[3:1]=active 截断无害） |
| W104 | 10 | **18**（召回↑） | body 端口方向/宽度缺失（tv80 旧式端口）——协议 body_port_rules 补全 |
| W002 | 33 | 33 | tpc_marker 残留（宏展开语句体 marker 未替换——深水区） |
| NC 族 | ~1300 | ~1300 | 默认命名 pattern（小写下划线）对真实代码误报海啸——**规则默认策略决策项** |

**剩余误报源评估**（宏展开深水区，不急于修）：
- W002 33：展开后 tpc_marker 占位未替换为宏体（语句体宏机制，P1.5 相关）
- W105 10：宏条件编译分支并存（picorv32 ifdef AXI/非 AXI 双分支展开保留）
- ice40 单元库 W201 20：yosys 仿真单元参数化端口（Q=D 16→1）宽度语义
- 命名类：NC001-013 默认全开 + 小写下划线 pattern → 真实代码（混合风格）
  大量触发——**0.1.1 暴露前必须定默认启用策略**（默认关 NC 或按语言包
  声明默认集；规则=数据，用户可覆盖）

**合理检出**（非误报）：UN001（真未使用，darkriscv OPCODE 等）、CC001/
LC001（真风险）、W101（跨文件定义缺失——单文件语料预期行为）、W103
（单元库参数覆盖核对）。

**结论**：真实误报率在语义规则（W 族）已压到低水平（W105 10 / W201 31
中还有宏深水区成分）；**瓶颈在命名类默认策略**（决策项）+ 宏展开完整
性（W002/W105，P3 增量解析前置）。check 宏展开使真实工程可用了。

#### 命名规则配置面设计（2026-08-29，默认关已落地，前后缀下一期）

背景：试水实测 NC 族默认全开 + 小写下划线 pattern 对真实代码（混合
风格）~1300 条误报海啸。用户定调（2026-08-29）：命名风格主轴 = 蛇形 +
大小驼峰；比风格更有价值的是**前后缀语义约定**（防错）。

**已落地（提交 e93ab9f 等）**：
- `[[checks]] default = false`：NC 族默认关闭（规则=数据，语言包声明）
- 启用语义（analyzer/checks.py）：显式 enabled = "不选即关"（P4 不变）；
  缺省 = default=true 的规则 ∪ overrides/per_file **引用即启用**（per_file
  豁免对默认关闭的规则才有意义）；ProjectChecker.enabled_rules 注入
  （评测/测试显式启用）
- NC001/NC002 模块/实例 pattern 放宽为 **PascalCase 或 snake_case**
  （行业惯例；真实语料 picorv32/serv 均 Pascal）
- 默认关后真实语料 NC 诊断归零（默认体验不刷屏；启用才按团队约定查）

**配置面（2026-08-29 落地）**：
- 前后缀语义约定（防错）——声明式表 + handler（name_check/rules/
  _prefix_suffix_check.py）：
  - **NC014 端口方向后缀**：`direction_suffix` 表（input→_i / output→_o /
    inout→_io）——名字以某方向后缀结尾但声明方向不同 → 方向可能接反
    （防错核心，强约束）；规则数据 `require = true` 时未按本方向后缀命名
    也报（强约定模式）
  - **NC015/NC016 类型后缀**：`kind_suffix` 表（wire→_w / reg→_r）——
    wire 带 _r / reg 带 _w → 类型可能混淆；require 模式补本类型后缀要求
  - 豁免：`_` 前缀（占位/故意不用约定，与 unused_check 同语义）
  - 默认关（default=false），启用走 P4 用户配置 enabled（NC 族机制已有）
- **评估不做**：低有效 `_n`、时钟/复位前缀 `clk_`/`rst_`——Verilog-2005
  无 clock/reset 符号 kind，用途判定需事件控制/复位条件分析（主流 svlint
  亦无此类规则，仅端口 prefix_input/output/inout）；用户可按团队约定自写
  pattern 规则（配置面扩展点）
- 风格表（per kind）与豁免完善（单字母/`tpc_` 前缀）：后续按需，配置面
  机制已就绪
- 默认策略：风格弱约束（只报混用）/前后缀强约束（声明了才查）——0.1.1
  默认 NC 关，启用走 P4 用户配置

#### 核心检查项目缺口集合 + 剩余误报源评估（2026-08-29 盘点）

**一、核心检查项目（P1.10 十类）状态与残余缺口**

| 类 | 规则 | 状态 | 残余缺口 |
|---|---|---|---|
| 命名 | NC001-016 | ✅ 闭环（默认关） | 前后缀配置面已落地（NC014-016，方向/类型后缀表）；`_n`/clk_/rst_ 评估不做（无 kind 支撑） |
| 未使用 | UN001 | ✅ 闭环 | 无（parameter/`_` 豁免已有） |
| 位宽 | W201/W202 | ✅ 主流程闭环 | 算法性有意截断无法区分（跨模块成员宽度已补——hier 插件 2275a06） |
| 锁存 | LC001 | ✅ 闭环（2026-08-29 升级全路径判定） | 有意锁存（单元库 SR/IO 锁存模型，真实语料 25 条全为此类）如实报、lint_off 处置；循环/参数边界不可判时保守 ∅（见下"三主题实现机制调研"） |
| case | CC001 | ✅ 闭环 | 无（casex/casez 覆盖） |
| always 写法 | AW001/AW002 | ✅ 闭环（2026-08-29，默认关） | 裸 always 无事件控制仍不做（仿真合法，误报高）；AW 族默认关 + lint_off 处置（见下"三主题实现机制调研"） |
| 端口 | W104 | ✅ 闭环 | 无（位置连接已按声明序匹配，b571d40） |
| 实例化 | W101-103/WC001 | ✅ 闭环 | W103 对单元库定义不完整的代码报（合理检出） |
| 多驱动 | W105 | ✅ 闭环 | 无（跨模块同名已修，语义展开后真实语料归零） |
| 宏卫生 | linter 层 | ✅ | 宏展开深水区见下 |

**二、剩余误报源评估（真实语料，2026-08-29 最新）**

| 误报源 | 数量 | 性质 | 处置 |
|---|---|---|---|
| W002 marker | 0 | ✅ 已修（语义展开 b543b97） | 闭环 |
| W105 宏条件分支 | 0 | ✅ 已修（语义展开顺带修复） | 闭环 |
| W201 移位截断 | ~11 → 10（picorv32） | 对拍修正（2026-08-29，V3Width 源码级）：`a = b >> 32`（64→32）**Verilator 也报** WIDTHTRUNC——widthBad 判据对 sized 表达式只看全宽，最小宽度抑制仅限 unsized 常量；"Verilator 也不报"系此前未经对拍的误判。10 条 = 显式取位/算法性但主流同样报 | 保留报（与 Verilator 一致）；已修 `!` 逻辑非宽度 bug（pcpi_timeout 4→1，IEEE 5.5 逻辑运算 1 位，1 条真误报） |
| W201 算法性截断 | picorv32 部分 | 真截断但算法有意（64 位除法窄寄存器逐步） | 保留报（用户判断）或降 info |
| W201 单元库 | 20 → **0**（ice40） | ✅ **跨模块同名符号污染（真 bug，已修）**——SB_MAC16 的 `[15:0] D` 污染 20 个 SB_DFF 的标量 D，20 条 W201 全 FP；此前落档"已知边界不修"系未查根因。修复：宽度表按模块作用域隔离（_lookup_width 限定键） | 闭环（对标测试 2026-08-29 推翻旧结论） |
| W103 单元库参数 | 79 → **0**（ice40） | ✅ **模块体参数提取缺口（真 bug，已修）**——SB_RAM40_4K 参数在模块体（`parameter P = v;`）非头部 #(..) 列表，_fill_params 只收头部 → module_index 参数空 → 79 条"覆盖不存在参数"全 FP；此前落档"合理检出/语料不完整"系未查根因。修复：_fill_body_params 扫 ParamDeclStmt | 闭环（对标测试 2026-08-29 推翻旧结论） |
| W104 函数参数误当端口 | 8（tv80） | ✅ **函数/任务局部 input 被 _fill_body_ports 全子树遍历误收**（AddSub4 的 A/B/Sub/Carry_In 与模块体端口同节点名 BodyInputDecl）→ 8 条假 W104；Verilator 0 报 PINMISSING。修复：跳过 FuncDecl/FuncDeclOld/TaskDecl 子树 | 闭环（对标测试 2026-08-29） |
| CC001 全覆盖误报 | 7（ice40 4 + tv80 3） | ✅ **只看"有无 default 关键字"不看覆盖完整性**——`case(cc)` 8 值全覆盖 / `case(WRITE_MODE)` 2 位 0-3 全覆盖无锁存风险，Verilator 0 报 CASEINCOMPLETE。修复：复用 latch_check _case_covered 判据（常量全覆盖不报） | 闭环（对齐 Verilator CASEINCOMPLETE，2026-08-29） |
| W105 generate 互斥分支 | 8（picorv32） | ✅ **generate if/else 互斥分支被信号图同时计入驱动**——Verilator V3Param 展开后未选中分支物理删除（deleteTree），多驱动只看到选中分支。修复：_in_active_generate 沿祖先链求值 generate 条件（参数表），未选中分支驱动跳过；不可判保守保留。详见下"generate 互斥分支机制调研" | 闭环（对齐 Verilator V3Param，2026-08-29；此前标"层 3 未展开已知边界"系未查机制） |
| NC 命名 | ~1300 → 0 | ✅ 默认关已处理（0b83b7e） | 闭环 |

**三、当前真实误报率（对标测试后，2026-08-29）**：语义规则 W201 30 → 10（ice40 20 条跨模块同名污染已修）+ W103 79 → 0 + W104 8 → 0（tv80 函数参数误收已修）+ CC001 7 → 0 + W105 8 → 0（picorv32 generate 互斥已修）+ NC 0（默认关）+ LC001 25（单元库有意锁存，Verilator 对无实例化库单元跳过、simcells 22 条共识）；已知边界 = 算法性截断 10 + UN001 粒度（Verilator 按位/参数细化）+ AW 族默认关 + serv_top 语料不完整（W101，缺子模块）。

#### 试水第四弹：对标测试（2026-08-29，Verilator 二进制 oracle）

- 定位：变异注入器（第三弹）验证"错误能检出"，本弹验证"与成熟工具输出
  一致性"——同一输入分别跑 tpc check 与 Verilator --lint-only -Wall，
  差异按处置三选落地。**从源码级判据（W201 对拍 V3Width）升级为二进制
  全量对拍**。
- 工具链：MSYS2 装 Verilator 5.050（winget 装 MSYS2 → pacman 装
  mingw-w64-x86_64-verilator；verilator 是 perl 包装脚本，须在非 login
  bash 下跑——harness 用临时 .sh 承载，直接调 verilator_bin 会因 MSYS
  路径前缀失败）。
- 实现：`tests/e2e/eval_benchmark.py`——工程分组喂双侧 + W 码↔tpc 码
  映射表（W2T）+ 三态判定（共识/仅 tpc FP 候选/仅 V 漏报候选）+
  **lint_off 抑制识别**（picorv32 源码 lint_off WIDTH——"Verilator 不报"
  是被抑制不是判断一致，44 条 tpc 诊断正确归为"抑制"非 FP）+
  **条件编译行号偏移处理**（ifdef 展开后行号 ≠ 源行号，P3.3 已知坑；
  含条件编译文件按码族数量对齐，simcells 22 条 LC001=LATCH 22 条共识
  由此正确识别）+ parse 失败标 TPC-PARSE-FAIL（darkriscv P1.5，0 诊断
  是假干净不算 MISS）。
- 结果（真实语料 7 工程）：
  - **共识 44 条**：UN001↔UNUSEDSIGNAL 21（tv80 13 + picorv32 8）、
    LC001↔LATCH 22（simcells 单元库锁存）、UN001↔UNUSEDPARAM 1
  - **修复 4 个真 bug（106 条 FP → 0）**：W201 跨模块同名符号污染
    （ice40 20）+ W103 模块体参数提取缺口（ice40 79）+ W104 函数参数
    误当端口（tv80 8）+ CC001 全覆盖误报（ice40 4 + tv80 3）——前 2 条
    **推翻此前"已知边界/合理检出"落档**（未查根因）
  - **剩余差异全部判明类别**：仅 V 326 = AW 族默认关（BLKSEQ/COMBDLY）
    + UN001 语义粒度（Verilator 按位/参数报）+ 单元库未消费信号跳过
    （ice40 din_0 有意锁存，Verilator 对无实例化模块跳过 LATCH）；
    仅 tpc 26 = serv_top W101 13+W105 2（语料不完整缺子模块，Verilator
    同 MODMISSING）+ picorv32 W105 8（generate if/else 互斥分支被信号
    图同时计入驱动 = 层 3 未做 generate 展开的已知边界）+ ice40 LC001 3
    （有意锁存，LATCH_INPUT_VALUE 参数语义）
- 边界如实：Verilator 全设计 elaboration 视角 vs tpc 单文件+跨文件局部；
  评测集对拍（--acc）34 case 待跑（单文件 case Verilator 需 -Wall 过滤
  性能类，另行评估）；svlint（cargo）列为可选项未装


### Synopsys（商业 EDA 工具链）— 方法论参照（2026-08 调研，agent-reach + web 检索）

- 定位：1986 年创立、总部 Sunnyvale 的 EDA 巨头（NASDAQ: SNPS），与 Cadence 构成
  行业双寡头。对 tpc 的相关面是 Verilog 工具链三件套——**VCS**（编译型仿真）、
  **Design Compiler**（综合）、**SpyGlass**（lint/CDC 静态检查，见上"第三路"
  深调研），外加 **SDC**（声明式约束，行业事实标准）。**核心工具全部闭源商业
  授权**，官方 GitHub 开源存在度极低（`org:synopsys` 仅 1 个仓库；synopsys-sig/
  blackducksoftware 是 Black Duck 收购资产，SCA 扫描方向，与 HDL 无关）——
  **无代码可 fork，只做方法论参照**
- 存续状态：公司持续活跃扩张——2024-01 宣布 350 亿美元收购 Ansys（物理仿真扩展）、
  2025-12 NVIDIA 投资 20 亿美元（GPU 加速仿真/设计）、2023-11 加入 RISC-V
  （ARC-V 嵌入式核）；但工具无公开版本、无社区，<1.0 版本号概念不适用
- 管线结构逐阶段对比（各自前端形态，各有取舍非优劣）：

| 维度 | Synopsys 工具 | tpc |
|------|---------------|-----|
| 仿真前端 | VCS 三步法：analyze → elaborate → compile（产出 simv 原生可执行；增量编译只重编变更模块） | preprocess → lint → parse → analyze → transform → render |
| 综合前端 | DC：analyze + elaborate（全层次展开 + 参数具体化）→ compile → write | 单文件管线为主；inst_check 是"微型 elaboration"（跨模块端口/实例检查） |
| 静态检查 | SpyGlass：parse → Rule→Goal→Sub-Methodology 三层规则引擎 → 层级化报告；SGDC 约束压误报 + .awl waiver | linter（前置 token 级）+ semantic_check 插槽（P1.9 规则表待落地） |
| 约束/配置面 | SDC（Tcl 子集声明式约束）+ 各工具 Tcl setup 文件 | TOML 配置 + grammar 规则数据 |

- **亮点单独说明**：
  - 💡 **SDC 是"声明式约束即接口"的行业级先例**：Synopsys 把时序/面积/功耗约束
    做成 Tcl 子集声明语言，全行业（Intel Quartus、Microchip、对手工具）采纳为
    输入接口——商业 EDA 里"设计意图以数据形态跨工具传递"被验证可规模化。
    tpc 的"语法/布局/检查全是 TOML 数据"哲学同源，路径不同（工业接口 vs 引擎
    设计）；SDC 的成功佐证配置驱动方向在 EDA 域的长期价值
  - 💡 **Rule→Goal→Sub-Methodology 规则组织**（SpyGlass）：数千条规则按 goal
    （lint_rtl / CDC / Constraints / DFT / Power / TXV）分组、methodology 子集化、
    severity Fatal/Error/Warning/Info——tpc P1.9 规则表可加 `goal` 字段
    （对齐已有 `group`/`severity` 提案，见上"实现路径提示"）
  - 💡 **SGDC 约束压误报**：CDC 类高误报规则靠"设计约束声明"过滤假阳性——
    tpc 跨文件规则（inst_check W 系列）缺"连接约束"层，SGDC 式约束声明是降
    误报的参考形态（P1.9 后置；related 链已可承载约束链溯源）
  - 📌 **VCS 增量编译 / DC elaborate**：与 P3 增量解析同方向——elaboration 是
    跨文件语义分析的工业级形态；VCS"只重编变更模块"= P3.2"受影响单元重解析"
    的商业实证
  - 📌 **Ansys/NVIDIA 动向**：EDA 工具向"物理仿真 + GPU 加速"扩展——tpc 定位
    "语言流水线"而非全工具链，不追（README 边界已声明）
- **可实现性评估**：
  - 🔥 **可做（低成本）**：规则表 `goal` 字段（lint_rtl 式 goal 分组，与
    `group`/`severity` 一并进 P1.9 规则表 schema）
  - 💡 **可做（中成本）**：约束声明层——`[[checks]]` 或 analyzer 参数化约束
    TOML，供跨文件规则降误报（P1.9 后置，先验证 inst_check 误报样本）
  - 📌 **不做**：全 LRM 前端（VCS/DC 级解析）与仿真/综合——tpc 明确定位
    可综合子集 + 格式化/检查，商业级 parser 规模超出配置驱动引擎的合理范围
    （README Known limitations）；CDC 类深度语义检查同判远期（survey 已定）
  - ❌ **不借鉴**：闭源工具内部实现（无公开代码，无从借鉴）；Tcl 配置面
    （tpc 用 TOML 承载"规则即数据"，Tcl 是运行时脚本语言，形态不匹配）
- 来源：[Wikipedia Synopsys](https://en.wikipedia.org/wiki/Synopsys)、
  [VCS 三步法仿真流程](https://blog.csdn.net/weixin_45791458/article/details/143470583)、
  [DC analyze/elaborate 对比](https://blog.csdn.net/weixin_29230649/article/details/158856394)、
  [SDC 定义（Intel Quartus 术语表）](https://www.intel.la/content/www/xl/es/programmable/quartushelp/19.1/reference/glossary/def_sdc.htm)、
  [SDC 与 STA（EcrioniX）](https://ecrionix.org/sta/sdc/)、
  [NVIDIA 20 亿美元投资（The Register）](https://www.theregister.com/2025/12/01/nvidia_synopsys_2b/)、
  [Synopsys 收购 Ansys（CNBC）](https://www.cnbc.com/2024/01/16/synopsys-to-acquire-ansys-in-35-billion-graphics-software-deal.html)、
  [Synopsys 加入 RISC-V（The Register）](https://www.theregister.com/2023/11/07/synopsys_joins_riscv_party_with/)

#### 位宽 / 锁存 / always 写法——三主题实现机制调研（2026-08-29，源码级）

- 定位：P1.10 调研停留在"规则族清单"层（谁有哪条规则）；本次下沉到**实现机制**层
  （怎么算宽度、怎么判锁存、怎么管 always 写法）。来源：Verilator（warnings.rst、
  V3Active.cpp、V3Width 三段式、LATCH 引入提交 a117002）、slang（diagnostics.txt、
  OperatorExpressions.cpp、Analysis 数据流层）、Yosys（proc_dlatch.cc/proc_dff.cc）、
  svlint（ruleset-simsynth + 规则说明）、Verible（style_lint.md + always-* 规则源码）、
  Icarus（iverilog(1)）、SpyGlass（闭源，仅规则形态可见）

**一、位宽分析——实现机制对比**

| 工具 | 机制 | 关键设计 |
|---|---|---|
| Verilator | V3Width.cpp（表达式宽度推断）+ V3WidthSel.cpp（select/索引宽度）+ V3WidthCommit.cpp（转换插入）三段式 | 自定宽/上下文定宽两遍（IEEE 5.5）；WIDTH 汇总码 = WIDTHEXPAND/WIDTHTRUNC/WIDTHXZEXPAND；**unsized 常量最小宽度追踪**（够容纳即不报）；WIDTHCONCAT（concat/复制内未定宽项） |
| slang | AST 类型传播 + 每表达式 `getEffectiveWidth`（有效宽） | width-expand/trunc（隐式转换）、**port-width-expand/trunc（端口连接独立成码）**、unsized-concat、range-width-oob；有效宽含 unsized 常量前导 X/Z 修剪（`'0` 全零匹配）；`group conversion` 诊断分组 |
| Icarus | elaboration 期宽度检查 | `-gstrict-expr-width`（unsized 常量不截断到 32，严格模式报错）+ `+width-cap`（unsized 表达式宽度上限）；默认宽松 |
| SpyGlass | W164a/b（赋值截断/扩展分码） | 闭源仅形态可见 |
| tpc 现状 | A1 符号宽度表 + A2 常量求值 + A3 infer_expr_width（5.5 语义） | W201（赋值/端口截断）；unsized 常量 → 保守 None（无最小宽度追踪） |

**二、锁存检测——实现机制对比**

| 工具 | 机制 | 关键设计 |
|---|---|---|
| Verilator | V3Active.cpp `LatchDetectGraph`：按组合 always 建控制流图（if/else 顶点），**逐被赋值变量遍历"全路径是否都赋值"** | LATCH（建议 always_latch）；always_latch 无锁存 → NOLATCH（期望反转）；ALWCOMBORDER（先读后写→状态保持暗示） |
| slang | Analysis 层数据流分析（DataFlowAnalysis/DriverTracker/ValueDriver） | inferred-latch "not assigned on all control paths"；另有 inferred-comb |
| Yosys | proc → proc_dlatch：进程同步类型判定（电平敏感无边沿）+ 赋值 mux 树**反馈位（hold=自身）**判定 | `-latches info/warn/error` 政策；always_comb 推断锁存 → error、always_latch 无锁存 → error（对称反转） |
| SpyGlass | W442aL（latch 推断） | 闭源仅形态可见 |
| tpc 现状 | LC001 有限版：组合 always 内 if 无 else | 只覆盖 if 形态；case 多臂/嵌套/全路径判定不做 |

**三、always 写法——实现机制对比**

| 工具 | 规则 | 机制 |
|---|---|---|
| Verilator | BLKSEQ（时序块阻塞赋值，**默认关** style 码）、BLKANDNBLK（混用阻塞/非阻塞，5.038 后收敛为"无法证明子位不重叠且阻塞赋值在组合逻辑"才报）、ALWNEVER（always @* 无读取变量→永不执行）、CASEINCOMPLETE | 语义 AST 分析；BLKANDNBLK 做子位重叠证明（建议 split_var） |
| svlint | blocking_assignment_in_always_ff/_latch、non_blocking_assignment_in_always_comb、general_always_no_edge、case_default、keyword_forbidden_* | 语法规则 + **LRM 条款引证**（每条挂 IEEE1800 章节）+ companion 规则互引；ruleset-simsynth 专门收"仿真/综合不一致"族 |
| Verible | always-comb（禁 always @*，**带 autofix**）、always-comb-blocking、always-ff-non-blocking、case-missing-default | 语法层 CST matcher |
| SpyGlass | W527（悬空 else）、W415a（if 分支双赋值） | 闭源仅形态可见 |
| tpc 现状 | 评估不做（2026-08-29 记录：裸 always 仿真合法误报高） | — |

**四、亮点单独说明**

- 🔥 **锁存全路径判定是最值得搬的算法**：Verilator 图遍历（逐变量×路径覆盖）与 slang
  数据流是同一判定的两种实现，都比"if 无 else"精确——覆盖 if-else-if 链、case 臂、
  嵌套。tpc LC001 升级路径明确：analyzer 语句树 + 被赋值变量集合×路径覆盖（信号图已
  有 (module, signal) 键，缺语句级控制流）。Yosys 反馈位判定是综合视角，互补（各有
  取舍非优劣）
- 🔥 **unsized 常量最小宽度追踪**（Verilator WIDTH 抑制 / slang 有效宽 X/Z 修剪）：
  `'0`/`3'd0` 的语义差别——tpc 现在 unsized → 保守 None，是压 W201 误报的低风险增量
- 💡 **端口连接宽度独立成码**（slang port-width-*、SpyGlass W164a/b 分截断/扩展）：
  W201 端口检查可拆方向码，对齐主流
- 💡 **期望反转 + 政策化上报**（NOLATCH / yosys `-latches` 政策）：有意锁存（总线保持）
  是高频合理用法——"保留报 + 降级 info + lint_off"优于"关掉"；tpc `default` 字段
  机制已可承载（0b83b7e）
- 💡 **默认关 + style 分类是"合法但易错"写法的标准处置**：Verilator BLKSEQ 明确默认关、
  svlint 独立 ruleset-simsynth、slang-tidy synthesis 组——tpc 之前"always 写法评估
  不做（误报高）"应修订为"**可做 + 默认关**"（与 NC 家族同构）；但须细分：裸 always
  无事件控制（仿真合法循环）主流也没禁（svlint 仅提示升级），保持不做；可做的是
  阻塞/非阻塞纪律族（2005 可表达）
- 💡 **svlint LRM 条款引证 / Verible autofix**：规则 message 挂 IEEE 条款号（tpc 可加
  `lrm` 字段）；autofix 超出 tpc lint 定位不搬，但"修复建议文本"值得学
- 📌 ALWNEVER（always @* 无读取变量→永不执行）低频有趣，远期候选

**五、可实现性评估（对 tpc）**

- 🔥 可做（低成本）：W201 低位宽抑制——unsized 常量最小宽度追踪（`'0` 全零/前导 X
  修剪），压误报，插件层
- 🔥 可做（中成本）：LC001 升级全路径判定——Verilator 式控制流图，覆盖 case/嵌套，
  analyzer 语句层；三大主题里机制价值最高的一个
- 🔥 可做（低成本，默认关）：always 写法风格族——时序块阻塞赋值（BLKSEQ 类）、
  混用阻塞/非阻塞（BLKANDNBLK 简化版）、case 无 default（CC001 已有部分覆盖）；
  语法层纯结构规则，零 handler
- 💡 可做（低成本）：W201 截断/扩展方向分码；规则 message 加 `lrm` 条款字段
- 📌 不做：WIDTHCONCAT 类（2005 concat 内 unsized 项 = 32 位合法，误报面大）、
  ALWNEVER（低频）、autofix（超出 lint 定位）、Yosys 式综合视角锁存（tpc 无综合后端）
- 来源：[Verilator warnings 文档](https://verilator.org/guide/latest/warnings.html)、
  [LATCH/NOLATCH 引入提交 a117002](https://github.com/verilator/verilator/commit/a11700271fc0c681bb1869bf6a299ff594c4028a)、
  [slang diagnostics.txt](https://github.com/MikePopoloski/slang/blob/master/scripts/diagnostics.txt)、
  [slang OperatorExpressions.cpp](https://github.com/MikePopoloski/slang/blob/master/source/ast/expressions/OperatorExpressions.cpp)、
  [yosys proc_dlatch.cc](https://github.com/YosysHQ/yosys/blob/main/passes/proc/proc_dlatch.cc)、
  [svlint ruleset-simsynth](https://github.com/dalance/svlint/blob/master/md/ruleset-simsynth.md)、
  [svlint general_always_no_edge](https://github.com/dalance/svlint/blob/master/md/syntaxrules-explanation-general_always_no_edge.md)、
  [verible style_lint.md](https://github.com/chipsalliance/verible/blob/master/doc/style_lint.md)、
  [iverilog(1) manpage](https://man.freebsd.org/cgi/man.cgi?query=iverilog&sektion=1)

#### 知名 AGENTS.md/指令文件范式调研（2026-08-29，见贤思齐）

- 定位：调研业界对"agent 指令文件（AGENTS.md/CLAUDE.md）怎么写才有效"的成熟
  共识，反哺 tpc 自己的 AGENTS.md（刚连续补了多条范式，正需要"指令文件自身的
  纪律"）。来源：agents.md 开放规范（agentpatterns-ai，Linux Foundation 旗下
  Agentic AI Foundation 治理，60k+ 项目采用）、Anthropic 官方 CLAUDE.md 指南、
  Tembo 综述（2026-06）、sqlite AGENTS.md 实例（125 行）、"AGENTS.md 作目录
  而非百科"模式文档（引用 OpenAI Harness 工程结论）

**一、来源对比**

| 来源 | 核心主张 | 与 tpc 现状的关系 |
|---|---|---|
| agents.md 开放规范 | 项目导向非文档：含"项目是什么(2-3 句)/约定位置/非显然约束/起步步骤"，不含"约定本身/架构文档/流程步骤"（一律链接）；~100 行指针 | tpc 已部分指针式（MODEL_INDEX/docs/decisions 链接）；行为范式内联但文件 ~100 行在预算内 |
| Anthropic CLAUDE.md 指南 | 文件进 system prompt 故须精简；渐进披露（拆分子文档再引用）；只加真实痛点（"Each addition should solve a real problem"）；持续维护非一次性 | "只加真实痛点"与我们按实际摩擦加范式一致；渐进披露 tpc 部分采用（references.md 承接调研） |
| Tembo 综述 | 命令优先于散文（"Run pnpm test" 优于"我们有完整测试策略"）；写告诉新同事的话；**不复制 linter**（一行"风格由 linter 强制"胜过四十条规则）；漂移警告（引用已删脚本比没有更糟）；从小处开始按证据增长；提交进 git | "不复制 linter/门禁"对我们有新意：测试门禁/工具强制的项不必在 AGENTS.md 重复 |
| sqlite AGENTS.md | 125 行实例：项目性质+非显然约束（public domain/不收 agentic 代码/Fossil 非 Git）→ 构建/测试命令（可复制）→ 单行架构管线 → **"不要编辑生成文件"表**（含再生成命令）→ 编码约定 → 参考链接 | "不要编辑生成文件"与"语言知识不进代码"同构（改 grammar TOML 不改引擎）——同是"改源头不改产物" |
| TOC 模式（OpenAI Harness） | 单体文件四败：上下文挤占/注意稀释/范围不可验/即腐；解法=指针图+版本化 docs；**规则生命周期元数据 Source/Applicability/Expiry**；"已能正确做就删"（Anthropic 同：agent 无指令也做对 → 删或转 hook）；机械保鲜（CI 断链/未引用检测） | 生命周期元数据对我们有新意；"已能正确做就删"与不留向后兼容/完成即删同向，但只管到代码没管到指令文件本身 |

**二、亮点单独说明**

- 🔥 **指令文件的删除谓词（"已能正确做就删"）**：Anthropic/TOC 模式共识——指令
  文件自身需要修剪纪律：某条指令 agent 没有它也稳定做对 → 删掉或转 hook；过期
  指令比没有更糟（Tembo 漂移警告）。tpc 的"完成即删/不留向后兼容"管 TODO 与
  代码，**没管 AGENTS.md 自身**——刚连加多条范式后正需要这条
- 🔥 **规则生命周期元数据（Source/Applicability/Expiry）**：每条规则带"为什么加
  /何时适用/何时可删"，删除从开放判断变封闭谓词——与我们"不留向后兼容"同纪律
  的指令文件版
- 💡 **不复制 linter/门禁**："风格由 linter 强制，修它报的就行"——AGENTS.md 不
  重复测试门禁/工具已强制的项，省上下文预算
- 💡 **命令优先于散文**：能写命令不写描述（sqlite 构建/测试节直接可复制）——tpc
  的"运行/测试"节已是命令式，保持
- 📌 **上下文预算**（ETH Zurich 评测：指令文件使推理成本平均 +20%）：文件保持
  ~100 行量级；后续范式沉淀优先进 references.md 而非 AGENTS.md（已在做）
- 📌 **"改源头不改产物"**（sqlite 生成文件表）：tpc 已有更严版本（语言知识不进
  代码 + 引擎零硬编码门禁），无需新增

**三、可实现性评估（对 tpc AGENTS.md）**

- 🔥 可做（低成本）：新增"指令文件修剪"纪律——某条范式 agent 无指令也稳定执行
  即删（与 TODO 完成即删并列，进 AGENTS.md 协作行为范式）
- 💡 可做（低成本）：给现有范式块补"何时可删"一行（删除谓词，与不留向后兼容
  同构）
- 💡 可做（中成本）：行为范式迁 docs/ 的 conventions 文件、AGENTS.md 只留索引
  （指针化）——个人项目暂不必要（文件仍在 ~100 行预算内），观察增长再动
- 📌 不做：逐条三字段元数据（Source/Applicability/Expiry 标注）——对 ~6 条范式
  过重，"何时可删"单行已够
- ❌ 不借鉴：自动生成指令文件（Tembo 明确反对：生成物缺最重要的架构决策）；
  monorepo 嵌套 AGENTS.md（tpc 单仓单文件）
- 来源：[agents.md 开放规范](https://agents.md)、
  [Anthropic: Using CLAUDE.md files](https://claude.com/blog/using-claude-md-files)、
  [Tembo: What Is AGENTS.md? How to Write One in 2026](https://www.tembo.io/blog/agents-md)、
  [sqlite AGENTS.md（GitHub 镜像）](https://github.com/sqlite/sqlite/blob/master/AGENTS.md)、
  [AGENTS.md as Table of Contents, Not Encyclopedia](https://github.com/agentpatterns-ai/website/blob/main/instructions/agents-md-as-table-of-contents.md)、
  [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)、
  [ETH Zurich 评测（上下文成本）](https://arxiv.org/abs/2602.11988v2)

#### 层次引用（a.b）解析机制调研（2026-08-29，见贤思齐 → 层次展开能力设计）

- 定位：TODO「位宽跨模块成员宽度」的前置调研——主流工具如何解析层次引用
  `a.b`（a = 实例，b = 被实例化模块的端口/内部成员），为 tpc 设计"专门的
  分析器插件能力"（用户定调 2026-08-29）。来源：slang（HierarchicalReference
  .cpp / Lookup.cpp）、Verilator（V3LinkDot.cpp）、Yosys（hierarchy pass）、
  tpc 自身 analyzer 结构核对

**一、逐工具机制对比**

| 工具 | 机制 | 关键设计 |
|---|---|---|
| slang | Instance 符号带 InstanceBodySymbol（模块全部成员入 body）；层次引用 = Lookup **逐段下钻** instance → body → member，宽度/方向取解析到的符号类型；`result.path` 记录遍历链 | 实例即符号对象、成员即其符号表——**按需解析，无显式"展开"** |
| Verilator | V3LinkDot `VSymGraph`：按层次建符号表（cell 名 + 模块名作用域树）；`findDotted` 逐段解析，未命中**沿层次上溯**（先 cellnames 后 modname） | **全量 elaboration**（模块实例化为 cell）；宽度来自解析后实际 VarRef 声明 |
| Yosys | hierarchy pass：cell 类型解析 + 模块树展开（综合视角） | 面向综合的层级展开，非 lint 语义 |
| tpc 现状 | HierExpr 纯成员链查**当前文件宽度表**（单模块视角）；`a` 是实例时查表不到 → 保守 None | 缺"实例 → 模块 → 成员"解析链 |

**二、亮点单独说明**

- 🔥 **slang 按需解析（实例即符号、成员即符号表）与 tpc 最同构**：tpc 已有
  module_index（端口表 + 参数 + **ModuleInfo.node 可走查内部成员声明**）+
  inst_sites（实例点）+ B3 三层参数合并——数据全齐，缺的只是"解析链"本身
- 🔥 **解析链 = 实例头 → 模块端口表（含覆盖参数）→ 内部成员（走查目标模块
  AST 声明）**：`a.b.c` 递归（a 实例 → 模块 N；b 若是 N 的实例再下钻 c）
- 💡 **Verilator 上溯回退**（当前模块找不到向上找）：SV 层次语义，2005 可综合
  子集少见，tpc 单文件视角暂不需要
- 📌 **全量 elaboration（Verilator）对 lint 过重**：tpc 按需解析即可，不实例化

**三、可实现性评估（tpc 层次展开能力设计）**

- 🔥 **可做（中成本）——hier 解析器插件（独立 postpass，语言知识留插件层）**：
  - per-module 实例表：module → {inst_name: (module_name, 实例点 site)}（本文件
    inst_sites 按模块归组；内部成员声明从 ModuleInfo.node 子树走查声明节点）
  - 链式解析 `a.b.c`：头段 a 查当前模块实例表 → module_index[模块].ports[b]
    （宽度表达式 + B3 覆盖参数合并）→ 非端口则走查目标模块 node 内部声明 →
    若是实例再下钻；解析结果 (width, direction, 模块链)
  - 消费方：width_check `_hier_width` 查不到本地表时回调 hier 解析器（替代
    保守 None）；direction 供未来跨模块悬空/驱动判定增量
- 💡 可做（低成本追加）：`a.b` 方向跨模块（input/output）——与未连接端口/
  驱动检查同族，后续规则可消费
- 📌 不做：上溯解析（SV 层次语义）、interface/class 成员（SV 特性）、全量
  elaboration（Verilator 式）、综合层级展开（Yosys 式）
- 来源：[slang Lookup.cpp](https://github.com/MikePopoloski/slang/blob/master/source/ast/Lookup.cpp)、
  [slang HierarchicalReference.cpp](https://github.com/MikePopoloski/slang/blob/master/source/ast/HierarchicalReference.cpp)、
  [Verilator V3LinkDot.cpp](https://github.com/verilator/verilator/blob/master/src/V3LinkDot.cpp)、
  [Yosys hierarchy pass](https://github.com/YosysHQ/yosys/blob/main/passes/hierarchy/hierarchy.cc)

#### 试水第三弹：变异注入器（2026-08-29，检查能力：错误类型 → 检出）

- 定位：手写精度样本（34 条）与真实语料之外，**系统化生成错误例子检验
  检查能力**——从正确基座程序化注入单个特定错误（变异测试），验证对应
  检查必然检出、注入不引发其他检查误报。与 fuzz 的关系：随机 fuzz 无
  ground truth 测不了检出；错误注入 = 有标签的定向 fuzz（先拆清
  "检查能力 vs 解析稳健性"：解析稳健性另轨，Verilator fuzzer 式）。
- 实现：`tests/e2e/mutation/`（injectors.py 注入器表 + eval_mutation.py
  运行器 + test_mutation.py 门禁）：
  - 注入器 = {正确基座 base（目标检查必须干净）, 单错误注入变换 mutate,
    目标检查, 默认关规则 enable, 合法连带 allowed_extra}
  - 运行语义：基座零诊断断言 → 注入后目标必检出（recall）→ 诊断 ⊆
    {目标} ∪ allowed_extra（无他检误报）→ 变异不破坏语法
  - 已覆盖 13 条注入（9 个检查）：W201 赋值/端口截断、W202 越界、
    LC001 if 删 else / case default 删赋值、CC001 删 default（连带
    LC001）、W104 命名删连/位置缺连、W105 双 assign/双实例 output、
    UN001 加未用声明、NC014 方向后缀改错、AW001 时序块改用 =
- 结果：**13/13 recall、基座 0 不干净、注入后 0 多余诊断、0 解析失败**；
  全量 1464 pytest 绿。中途发现 2 条注入器自身错误（有 default 的 case
  删臂不产生锁存 = 注入错误不成立；追加行落在 endmodule 外）——注入器
  的"错误必须真实"由门禁反向保证
- 扩展点：注入器表追加即可（每检查多基座变体、真实语料注入、W101-103/
  W106/WC001/LC 类后续）；fuzz（解析稳健性）为独立轨

#### 试水第四弹：对标测试（2026-08-29 立项，Verilator oracle）

- 定位：变异注入器（第三弹）验证"错误能检出"，对标测试验证"与成熟工具
  输出的一致性"——同一输入分别跑 tpc check 与 Verilator lint，差异按
  处置三选落地。对拍验证（AGENTS.md 范式）从"源码级判据"（W201 对拍
  V3Width）升级为"二进制 oracle 全量对拍"。
- 工具选型（2026-08-29 实测环境）：
  - **Verilator（MSYS2，主 oracle）**：语义检查最强，覆盖 W 族（位宽）/
    LATCH/UNUSED/CASE 类，与 tpc 检查链重合度最高；本机未装，winget 装
    MSYS2 后 pacman 装 mingw-w64-x86_64-verilator
  - Verible lint（已捆绑 tests/differential/.tools/verible/，零安装）：
    语法/风格向，~60 条，与 tpc 规则集重合低，作辅助参照
  - svlint（未装，cargo 可用）：规则集与 tpc 重合最高（159 条），但
    cargo install 编译耗时，列为后续可选项（如需安装再评估）
- 输入集：真实语料 9 文件（tests/e2e/samples/real/ref/）+ 评测集
  （tests/e2e/samples/check_accuracy/ 34 case）+ mutation 基座/变异体
- 差异归一化：tpc 规则码 ↔ Verilator W 码映射表（W201↔WIDTHTRUNC、
  LC001↔LATCH、UN001↔UNUSED、W105↔MULTIDRIVEN、CC001↔CASEINCOMPLETE、
  W104↔PINMISSING 等）；按 文件/行/规则 对齐
- 判定：两者都报 = 共识；仅 tpc 报 = FP 候选（查是否真误报）；仅
  verilator 报 = 漏报候选（规则缺口 or scope 外，逐条判）
- 边界如实：Verilator 是全设计 elaboration 视角，tpc 是单文件+跨文件
  局部；Verilator 的仿真/综合语义码（UNOPTFLAT/UNOPTIMIZED 等）超出
  lint 范围，先过滤不比对；Verilator 默认警告面宽（含性能类），用
  -Wall + 过滤表收敛到可比子集
- 处置三选：修（真缺口） / 降级（误报面大，参照 NC/AW 默认关先例） /
  记录为已知边界（scope 差异或工具行为差异）
- 阶段：① 装 Verilator 验证可跑 → ② 写对拍 harness（eval_benchmark.py）
  → ③ 真实语料 + 评测集对拍 → ④ 差异逐条处置 → ⑤ 结论落档

#### 试水第四弹执行结果（2026-08-29，Verilator 二进制全量对拍）

- 工具落地：MSYS2（winget）+ mingw-w64-x86_64-verilator 5.050（pacman）。
  verilator 是 perl 包装脚本，直接调 verilator_bin 会因 MSYS 路径前缀失败
  （/mingw64/share/verilator 找不到）；须在非 login bash 下跑（-lc 的
  login shell 环境 ulimit/exec 失败）——harness 写临时 .sh 承载。
- harness：`tests/e2e/eval_benchmark.py`——工程分组双跑（uart 三文件一组，
  其余单文件）+ W 码↔tpc 码映射表（W2T）+ 三态判定（共识/仅 tpc FP 候选/
  仅 V 漏报候选）。三个关键判据修正：
  - **lint_off 抑制识别**：picorv32 源码第 20-23 行 `verilator lint_off
    WIDTH/PINMISSING/CASEOVERLAP/CASEINCOMPLETE`——"Verilator 不报"是
    被作者主动关闭不是判断差异；44 条 tpc 诊断正确归"抑制"而非 FP 候选
    （此前"picorv32 10 条 W201 与 Verilator 一致"的源码级推断在此被
    二进制实证修正：一致是**默认判断**一致，非实际输出一致）
  - **条件编译行号偏移**（P3.3 已知坑实证）：simcells 580-596 的 ifdef
    块使展开后 token 行号 ≠ 源行号（偏移 16）——tpc 报展开后行号、
    Verilator 报源行号；含条件编译文件按**码族数量对齐**（simcells 22
    条 LC001 = LATCH 22 条由此正确识别为共识）
  - **parse 失败标定**：darkriscv parse_ok=False（P1.5 条件编译嵌套位置
    未根治）→ 0 诊断是"假干净"不算 MISS，标 TPC-PARSE-FAIL
- 真实语料 7 工程结果：
  - **共识 44 条**：UN001↔UNUSEDSIGNAL 21（tv80 13 + picorv32 8）、
    LC001↔LATCH 22（simcells 单元库锁存模型，Verilator 同报）、
    UN001↔UNUSEDPARAM 1
  - **修复 5 个真 bug（114 条 FP → 0，其中 2 条推翻旧落档）**：
    W201 跨模块同名符号污染（ice40 20）/ W103 模块体参数提取缺口
    （ice40 79）/ W104 函数参数误当端口（tv80 8）/ CC001 全覆盖误报
    （7）/ **W105 generate 互斥分支（picorv32 8）**
  - 剩余差异全部判明类别：仅 V 326 = AW 族默认关（BLKSEQ/COMBDLY）+
    UN001 语义粒度（Verilator 按位/参数报）+ 单元库未消费信号跳过
    （ice40 din_0 有意锁存，Verilator 对无实例化库单元跳过 LATCH）；
    仅 tpc 14 = serv_top W101 13+W105 2（语料不完整缺子模块，Verilator
    同 MODMISSING 硬错误跳过）+ ice40 LC001 3（有意锁存）
- 评测集 34 case 对拍：共识 11 条（W201 trunc×3/W202 oob×2/W104×2/
  LC001×2/UN001×1/CC001×1）核心检出一致；仅 tpc 10 条多为**正样例的
  正确检出**（W105/W106/UN001 是 tpc 规则语义，Verilator 无对应或判定
  不同）；仅 V 26 条为 UN001 粒度/行号错位/性能类——语义设计差异非缺陷

#### generate 互斥分支机制调研（2026-08-29，Verilator 源码级）

- 背景：picorv32 `generate if (ENABLE_MUL) 实例 else assign` 互斥分支
  被 tpc 信号图同时计入驱动 → 8 条 W105 假阳性（Verilator 0 报）。
- Verilator 机制（V3Param.cpp:3255-3276 `visit(AstGenIf*)`）：
  - 管线顺序：linkParse → linkDotPrimary → linkLValue → **V3Param**
    （参数折叠 + generate 展开）→ linkDotParamed → V3Width →
    V3WidthCommit → ...
  - 展开逻辑：求值 condp（widthGenerateParamsEdit 定宽 +
    constifyGenerateParamsEdit 常量折叠）→ 若为 AstConst：
    `keepp = (isZero ? elsesp : thensp); keepp->unlinkFrBackWithNext();
    nodep->replaceWith(keepp); nodep->deleteTree()`——**未选中分支随
    GenIf 一起物理删除**，后续多驱动检测（V3Width/V3LinkLValue 之后）
    只看到选中分支的驱动源。条件不可判 → 报错"Generate If condition
    must evaluate to constant"（Verilator 要求 generate 条件可判）
  - genfor 在 AstGenBlock::visit 展开（GenForUnroller）；gencase 类似
- tpc 对齐实现（analyzer/checker.py）：信号图收集驱动时 `_in_active_
  generate` 沿祖先链找 GenerateBlock→IfBlock/ElseIfBlock，条件用模块
  参数表求值（头部 + body 参数已合并），未选中分支的 assign/实例驱动
  跳过；**条件不可判 → True 保守保留**（不因无法判定漏报真多驱动，
  与 Verilator"报错"比是保守侧，避免引入语言知识外的求值器）
- 验证：最小复现 P=1/P=0 双跑 0 报、else-if 三链（ENABLE_FAST_MUL →
  ENABLE_MUL → else）0 报、**选中分支内真多驱动仍报**（u1+u2 双实例）、
  picorv32 8 条 W105 全消；3 个新测试进 test_checker.py

#### 试水第四弹扩展：三工具对照（2026-08-29 立项，Verilator + Verible + svlint）

- 定位：Verilator 单 oracle 对拍完成后，对照测试扩展到 **Verible lint**
  （已捆绑 tests/differential/.tools/verible/verible-verilog-lint.exe，
  零安装）与 **svlint**（Rust，规则集与 tpc 重合最高 159 条；本机 rustup
  无 toolchain，先 `rustup default stable` 再 `cargo install svlint`，
  编译耗时几分钟，后台装）。三个 oracle 覆盖不同检查维度：
  - Verilator：语义最强（位宽/锁存/未使用/多驱动）——已闭环
  - Verible lint：语法/风格向（~60 条，case 缺 default/命名/宏卫生），
    tpc 差分测试已带其 exe，规则 ID 稳定（verible-verilog-lint --rules）
  - svlint：规则工程化范本（159 条，命名族/宽度族/锁存族全谱），
    与 tpc 规则集重合最高——此前调研的"蓝本"落地为 oracle 实证
- 差异归一化：三 oracle 各自的规则 ID → tpc 规则码映射表（svlint 规则
  名如 explicit_case_default / verilator width_*；Verible 规则名如
  case-missing-default / line-length）；判定模型沿用 Verilator 对拍
  （共识/仅 tpc/仅 oracle），lint_off 抑制识别 + 条件编译行号偏移处理
  复用
- 边界如实：三工具输出格式不同（Verilator %Warning / Verible 文本 /
  svlint miette JSON）需分别解析；svlint 需要 cargo 装（~5-10 分钟）；
  Verible 默认规则集与 tpc 重合度低（风格向），对照重点在 case/命名
- 阶段：① 装 svlint（后台）② Verible lint 规则清单 + 探针 ③
  eval_benchmark.py 扩展多 oracle ④ 三工具真实语料 + 评测集对拍
  ⑤ 差异处置三选 + 落档

#### 试水第四弹扩展执行结果：三工具对照（2026-08-29）

- 工具落地：
  - **Verible**（已捆绑 tests/differential/.tools/verible/verible-verilog-lint.exe
    v0.0-4141，零安装）；输出 `file:line:col-col: msg [Style: x] [rule]`，
    `--help_rules=all` 列 60 条规则；`--ruleset=all` 全开
  - **svlint**（用户提供预编译 v0.9.5，E:\research\svlint\release\bin\
    svlint.exe；cargo install 因 Rust 1.98 与旧依赖 build script 不兼容
    失败——proc-macro2/winapi 等）；输出 miette ANSI 彩色格式
    （`Fail: rule` + `--> file:line:col`），须 strip \x1b 转义再解析；
    无 CLI 规则开关，默认全开 155 条规则，靠解析时映射表过滤
- harness 扩展（eval_benchmark.py）：_ORACLES 注册表（run 函数 + 码映射
  表 + 范围外码集），--oracle=name 可重复；_tpc_diags_all 覆盖文件组
  全部文件（oracle 扫全目录 vs entry 递归漏扫独立文件——project_bus_ctrl
  的 reg_if 不被 arbiter 依赖导致 CC001 漏报，修复后共识达成）
- 真实语料三工具对照结果（共识 66 = Verilator 44 + svlint 22）：
  | oracle | 共识 | 仅 tpc | 仅 oracle | 范围外 | 结论 |
  |---|---|---|---|---|---|
  | Verilator | 44 | 18 | 326 | 156 | 语义最强（位宽/锁存/未使用/多驱动），已闭环 |
  | Verible | 0 | 40 | 575 | 0 | 纯风格向（port-name-suffix/one-module-per-file），无语义重叠；默认规则集差异 = tpc NC 默认关 vs Verible 默认开 |
  | svlint | 22 | 62 | 8 | 999 | CC001 族语义重叠（22 条共识）；其余 999 风格规则范围外 |
  - svlint 共识 22 = explicit_case_default ↔ CC001（case 完整性双工具
    验证一致）；explicit_if_else 是风格规则（SV 要求显式 always_* +
    完整 if-else，时序也报）**不映射 LC001**（避免把风格差异当语义共识）
  - **能力域差异（重要结论）**：svlint 155 条规则无 unused/多驱动/端口
    完整性/锁存语义规则——单文件语法风格 lint，**不做跨文件语义**；
    tpc 的 UN001/W101/W104/W105/LC001 语义层 svlint 无对应 = 非漏报，
    是能力域差异。印证 P1.10 调研定论：**跨文件类（实例化端口/未使用/
    端口完整性）只有 tpc 能做**（svlint/Verible 单文件做不了）
  - inout_with_tri 严格度差异：svlint 要求 inout 必须显式 tri（裸 inout
    报），tpc W106 只报显式非 tri（裸 inout 默认 net 合法三态，Verilog-
    2005 宽容侧）——规则严格度选择非 bug
  - Verible 对 picorv32/tv80 ORACLE-SKIP（预处理宏 PICORV32_REGS 未定义
    报错——Verible 宏处理比 Verilator 严格），harness 标 SKIP 不当漏报
- 评测集三工具对照：Verible 共识 3（case-missing-default↔CC001）、svlint
  共识 4（explicit_case_default↔CC001）——case 完整性三工具一致；tpc 的
  语义规则（LC001/W104/W105/W201/W202/UN001）svlint/Verible 无对应 =
  能力域差异

#### 试水第四弹扩展：四工具对照完成（2026-08-29，+slang oracle）

- slang v11.0 落地：用户下载 slang-windows-x86_64.zip（E:\research\slang\
  slang.exe）+ 源码 tar（E:\research\slang-11.0，scripts/diagnostics.txt
  警告名全集）。--lint-only + 显式 -W 开启 + --diag-json 输出（JSON 数组，
  optionName + location file:line:col）。release 无 slang-tidy 二进制
  （独立构建目标），用 slang --lint-only 替代。
- 警告名映射（SLANG2T）：width-trunc/port-width-trunc/port-width-expand
  →W201、index-oob/range-oob/range-width-oob→W202、inferred-latch→LC001、
  case-incomplete/case-none→CC001、unused-* 族→UN001
- 结果：**评测集共识 5**（W201_trunc_assign/trunc_blocking/W202_index_oob
  等——位宽/越界族与 tpc 一致，第四 oracle 独立验证）；真实语料 0 共识
  （slang 语义警告需完整 elaboration 顶层，lint-only 对单文件大设计不
  触发）；仅 tpc = CC/LC/UN/端口族 slang 无对应 = 能力域差异实证。
  slang 无 multi-driven 警告（多驱动是 error 级或不做）。
- **W105 过程赋值驱动修复 + 性能回归（2026-08-29 注入器暴露）**：
  - 信号图原只收「连续赋值 + 实例 output」——`always @* y = c;` +
    `assign y = d;` 双驱动漏检。修复：收集过程赋值驱动（proc_assign_
    rules 协议字段），驱动源 = **过程块**（同一 always 内多赋值算一个
    驱动者，防同块分支赋值假阳性——picorv32 14 条假 W105 由此消除；
    不同块或 always+assign 才冲突，对标 Verilator MULTIDRIVEN）
  - 性能：过程赋值收集使 picorv32 单次 check 103s（_module_of/_in_active_
    generate 每节点全树扫描 = O(节点×树) 平方级）→ 预计算 generate 活性
    映射（_precompute_generate_active，单栈迭代 O(树) 查询 O(1)）→
    **5.8s（17.7x）**。过程赋值按块收集后同块多赋值不再每赋值一次
    _module_of，进一步提速
- **变异注入器 13 → 24 条（9 → 11 检查）**：W201 拼接/一元截断、
  W202 切片/+:越界、LC001 case default 删赋值/嵌套 if、CC001 casez、
  W105 always+assign（暴露上述修复）、W106 inout（新覆盖）、AW002 混用
  （新覆盖）、W104 inout 豁免负向（expect="clean" 机制新增）。门禁反向
  修正 5 处注入器自身设计错误（slice 越界算错/AW002 语义理解错/base 不
  干净 ×2/负向语义）。24/24 recall、0 FP、0 解析失败
- **并发测试默认开启**：pyproject addopts 加 `-n auto`（xdist 依赖本已
  声明）——全量 315s → ~87s（3.6x）；coverage 须 `-n 0` 关并发
  （xdist 每 worker 独立计数失真 61% < fail_under 80），CONTRIBUTING/
  release_checklist 已更新命令

##### slang-tidy 追查（2026-08-29，bin 里找不到？→ 官方从未打包）

- **结论：官方 release 从未包含 slang-tidy**。GitHub API 实测 v11.0 三个
  asset（slang-windows-x86_64.zip / linux / macos tar.gz）都**只打包
  slang.exe 单个 driver**；zip 内全部条目逐一核对只有 slang.exe。不是
  找错地方，是发布流程没打这个工具。
- 源码在 `tools/tidy/`（CMake 目标 `slang_tidy`，输出名 slang-tidy，
  SLANG_INCLUDE_TOOLS 默认 ON 一起编）。**本机 WinLibs 工具链自编成功**
  （cmake 4.4.1 + gcc 16.1 + ninja，FetchContent 自动拉 fmt/mimalloc）：
  `E:\research\slang-11.0\build-tidy\bin\slang-tidy.exe`（13MB，v11.0.0）。
- **22 个检查全部默认 ENABLED**：style 13（always-comb-non-blocking /
  always-ff-blocking / enforce-port-prefix/suffix / enforce-module-inst-
  antiation-prefix / generate-named / no-dot-star/var/implicit-port 连接 /
  no-legacy-generate / no-old-always-syntax / only-ansi-port-decl /
  always-comb-named）+ synthesis 9（no-latches-on-design / only-assigned-
  on-reset / register-has-no-reset / xilinx-do-not-care / cast-signed-
  index / always-ff-assignment-outside-conditional / unused-sensitive-
  signal / undriven-range / loop-before-reset）。
- 输出：`[CheckName] PASS/WARN/FAIL` + `file:line:col: severity:
  [STYLE-N]/[SYNTHESIS-N] message`（diag code 形如 STYLE-4 旧 always 语法、
  SYNTHESIS-3 锁存）。配置仿 .clang-tidy（`Checks:`/`CheckConfigs:` 段 +
  `--config-file`/`--print-descriptions`）。
- **与 tpc 交叉点实测**：NoLatchesOnDesign 用 AnalysisManager 驱动分析
  （getDrivers + `DriverSource::AlwaysLatch`），**只查显式 `always_latch`
  块**；`always @*` 部分赋值推断锁存走 slang 编译诊断 `InferredLatch`
  （即已接入的 -Winferred-latch）→ 两者互补不重复。tpc LC001 覆盖的是
  后者（推断锁存），口径 = slang 编译诊断而非 tidy 检查。
- 完整编译型工具（parseAllSources + createCompilation + runAnalysis），
  单文件不完整语料编译失败即退出；与 slang --lint-only 同类，跨文件语义
  检查在真实语料单文件上不触发（四工具结论不受影响）。风格类（旧 always
  语法/端口前后缀/实例前缀）单文件可跑，与 tpc 命名/风格规则可交叉验证。

##### slang-tidy 完成度源码级评估（2026-08-29，与对照组对比）

- **时间线**：v3.0（2023-03）引入，官方标注 "currently experimental"；
  v7.0（2024-09）才"加了一批新检查"；v8.1（2025-05）仍在修 crash；
  v11.0 至今 22 检查，未摘 experimental 帽子。多数检查为社区 PR
  （@Sustrak 框架 / @JoelSole-Semidyn 检查 / @spomata 复位族）。
- **框架层完成度高**（成熟产品水准）：仿 .clang-tidy 配置（Checks/
  CheckConfigs 段 + glob/组/severity 覆盖 + skip-file/path）、
  REGISTER+TidyFactory+TidyKind 插件注册、TidyDiags.h 诊断码集中管理、
  --print-descriptions/--dump-config/--code CLI 完备。底座是 slang
  AnalysisManager（getDrivers/ValueDriver/DriverSource）——真正深度的
  语义信息，NoLatches/UndrivenRange/复位族全部建在驱动分析之上，这是
  对照组（svlint 纯 AST 模式）没有的。
- **检查实现层完成度低**（玩具级）：
  - **4 个复位族检查是同一 visitor 复制粘贴**（OnlyAssignedOnReset /
    RegisterHasNoReset / AlwaysFFAssignmentOutsideConditional /
    LoopBeforeResetCheck，ConditionalStatement + LookupIdentifier 同一套）
  - reset 识别 = **字符串子串匹配**（LookupIdentifier exactMatching=false
    走 `name.find(name)`），非符号级；只认顶层一元 `~`/`!` 条件，
    `if (rst == 1'b0)` 形式不识别
  - UndrivenRange 假设 drivers 已按位序排列做线性扫描，偏移处理脆弱
  - CastSignedIndex 一个 handle 函数 5 行；XilinxDoNotCare 用
    SyntaxPrinter 重打文本再找 '?'（字符串扫描）
  - 风格类 EnforcePortSuffix ends_with 匹配合理但直白
- **测试层浅**：24 测试文件 ~125 case，多数检查仅正反例各 1（如
  NoLatchesOnDesignTest 2 case），单文件片段无真实工程回归；对比 slang
  主库数千 case 差一个量级。
- **结论**：框架先于规则成熟的典型——基建是工业级、规则与测试是
  实验级，官方自标 experimental 名副其实。与 svlint（159 规则 6 年）/
  Verible（~60 规则 8 年）/Verilator（136 W 码 30 年）比，规则数与测试
  深度差一个量级；但 AnalysisManager 底座让 NoLatches 口径（DriverSource
  级）比 svlint 纯语法模式高级，未来可期。对 tpc：检查实现深度（跨文件
  符号/generate 活性预计算）与测试深度（1467 + 24 注入器）已超它；可借鉴
  的是框架层（TidyKind 注册分类、诊断码集中管理、.clang-tidy 风格配置面）。

##### 不卫生宏体检测可行性（2026-08-29，原型验证 14/14）

- **背景**：checker 现为"一刀切全展开"（semantic=True 宏体替换，宏节点
  不入 AST）。原意图是带宏节点进 parse，但残缺片段宏（`= 1'b1`、
  `[3:0]`、`begin`/`end` 半截）会破坏语法边界让 parse 失败 → 只能全展开。
  设想：先做**宏体形态分类**（完整语法单元 vs 残缺片段），完整单元宏将来
  可保留为 MacroCall AST 节点，残缺宏维持原位展开。
- **方案：包装解析法 + 首 token 预过滤**（原型 tests/_proto_macro_hygiene.py
  验证 14/14 正确）：
  - 包装解析：宏体放进四种最小语法上下文试解析——语句位（module m;
    initial begin <body> end endmodule）、声明位（module m; <body>
    endmodule）、表达式位（module m; reg x; initial x = <body>;
    endmodule）、端口位（module m; input x <body>; endmodule）。任一
    成功 → 该形态完整单元；全失败 → 残缺片段。
  - **首 token 续接预过滤**（原型暴露的关键）：裸包装会把 `= 1'b1`
    （input x = 1'b1 恰好合法）、`+ 4`（一元正号）误判为完整——以
    `= [ ( , . + - * / & | ^ ~ ! ? :` 等续接 token 开头直接判残缺，
    消除上下文侥幸接受。
  - 实测：`initial Q = 0;`/`assign y = 1'b1;`/`if...else`/`reg` 声明
    → 完整语句；`1'b1`/`empty_statement` → 完整表达式；`= 1'b1`/
    `[3:0]`/`+ 4`/`begin`/`end`/`, .q(q)`/`else y = 2;` → 残缺片段。
- **推论（宏节点进 AST 前置）**：完整单元宏可保留 MacroCall 节点（宏调用
  + 展开体子节点），残缺宏维持展开——比"全展开"精确，展开量大幅下降；
  宏边界不再丢失（P3.3 行号反向映射也受益）。
- **设计约束**：包装模板是语言语法知识，不能硬编码进 Python——按
  proc_assign_rules 先例进 grammar TOML 协议字段（如 macro_hygiene_
  wrappers），引擎读配置（语言知识不进代码）。
- **延伸：预处理器宏策略配置化（2026-08-29 研判）**：P3.6 形态分类
  落地后，preprocessor/_expand.py 现存的 **5 种硬编码宏策略分支**
  可收敛为配置化策略表：① 行首空体宏（FORMAL_KEEP decl 修饰符）→
  整行占位；② 空 body 宏（TV80DELAY 行内占位）→ inline 注释锚；
  ③ `=` 开头 body（ice40 端口默认值）→ inline+body 区间还原（本质
  残缺片段）；④ 独占一行宏 → 补分号（语句体形态）；⑤ 普通宏 →
  token 锚 / semantic 宏体替换（完整单元形态）。这些 `startswith("=")`
  /single_head_empty/补分号规则全是 Verilog 特定启发式写死在引擎
  = **语言知识进代码的违例区**。收敛后：宏体形态（TOML 包裹模板
  判定）→ 展开策略（TOML 声明），预处理器从硬编码启发式变配置驱动
  策略执行器——与 grammar 侧"语言知识不进代码"同构。P3.6 形态分类
  是策略选择前提，分类能力一落地现有分支退化为策略表声明。

### 增量解析设计思考（2026-09-02）— 已迁 ADR-0009

> 设计输入已迁 `docs/decisions/0009-incremental-parse-design.md`（draft，
> P3.1-P3.6 共同设计输入）。本文件只保留外部项目调研；设计详案按
> 落档分流进 decisions/。


**文档调用点门禁设计（2026-09-02 用户发起，docs 精简后立项）**

> 背景：docs 精简（35→29 文件，删 config_reference / e2e_real_projects /
> case_catalog / comment_smell_rubric / comment_smell_survey / ieee1364
> annex）暴露文档管理痛点——文档增删改时调用点
> （代码 `Doc:` 头 114 处 / MODEL_INDEX 与 docs-README 索引 / `Impl:`/`Test:`
> 42 处）全靠人工 grep 核对；check_hardcode 的 R3 只查 `Doc:` 头**格式**
> （正则存在），不查**目标文件存在**——删文档门禁照样绿（本次实证）。
> 目标：机械可判的引用完整性 → 自动门禁，语义判断（符号级/章节锚点）
> 留给人工/模型。

- 分两层：**门禁层**（只读校验，进 CI，与 check_hardcode 并列）+ **同步层**
  （rename/delete 辅助写操作，二期，不进 CI）。
- 门禁规则（D1/D2 gate + D3/D4 警告）：
  - D1 代码 `Doc:` 头 → 目标 docs 文件存在（补 check_hardcode R3 缺口）
  - D2 导航索引（MODEL_INDEX / docs-README / README 文档表）→ 条目文件存在
  - D3 docs 内 `Impl:`/`Test:` → 文件级存在（`::` 符号部分 info 不 gate）
  - D4 新增 docs 文件未登记任何导航 → 警告（孤儿提醒，不阻断）
- 明确不做（边界纪律，与"语言知识不进代码"同构——语义判断不进工具）：
  符号级存在性（须 import 代码，脆且重）；CHANGELOG 历史条目自动改；
  正文叙述引用自动替换（`references.md「章节」` 含锚点语义）。
- 引用形态盘点：代码 `Doc: docs/...` 114 处 + 裸文件名 3 处（tests/fuzz、
  tools/policy——指向非 docs 目标，D1 只认 `docs/` 前缀）；docs 导航多为
  **裸文件名**（MODEL_INDEX `case_catalog.md` 形态）→ D2 按 docs 目录内
  文件名匹配，不假设 `docs/` 前缀；README 是 `./docs/` 相对链接形态。
- 落点：`tools/policy/check_doc_refs.py`（纯 stdlib，参照 check_hardcode
  的 Finding/RuleResult/--root/exit-code 结构）+ `tests/policy/` 单测 +
  CI policy step。同步层二期再落（`tools/doc_sync.py`：rename/delete
  列出引用点 + --dry-run 机械替换）。

**同步层设计（2026-09-02 用户确认立项，门禁 D1/D2 落地后）**

> 门禁层（check_doc_refs）解决"断链被发现"；同步层解决"改名/删除时
> 调用点一起改"——`tools/doc_sync.py`，复用 check_doc_refs 的引用解析
> （同一组正则 + `_resolve_nav_target`），保证"门禁认的引用 = 同步层改的
> 引用"，两边不漂移。

- 子命令（全部默认 --dry-run 只报告，--apply 才落盘）：
  - `refs <target>`：列出某 docs 文件被谁引用（代码 Doc: / 导航索引 /
    文档正文 / README / skills / TOML），每处 文件:行 + 引用形态
  - `rename <old> <new> [--apply]`：改 docs 文件路径 → 同步改全部引用点
    （`Doc: docs/old` / `./docs/old` 链接 / 裸名 `old.md` / `docs/old` 前缀）
  - `delete <target> [--apply]`：删除 docs 文件 → 先列引用点，--apply 时
    同步清引用并 git rm（引用含非机械可改处则拒绝并提示人工）
- 机械可改的引用形态（与门禁 D1/D2 的解析范围一致）：
  - 代码文件头 `Doc: docs/...`（行内整路径，机械可改）
  - 导航索引/正文里的 `docs/...`、`./docs/...`、裸 `xxx.md`（docs 根内
    文件名唯一时）——裸名只改"唯一指向该文件"的引用，歧义时跳过留人工
- 明确不做（同门禁边界）：`Impl:`/`Test:` 里 `::符号` 部分、正文叙述
  引用（`references.md「章节」` 锚点语义）、CHANGELOG 历史条目（历史
  不篡改，delete 时跳过）。
- 与门禁闭环：rename/delete 后用 `check_doc_refs.py` 验证 D1/D2 仍绿——
  同步层不绕过门禁，只是把"人工 grep 同步"变成"半自动 + 门禁兜底"。

**删除判据（2026-09-02 用户发起，2026-09-02 落档）**

> 背景：docs 精简 + __init__.py 清理中"什么该删"多次凭临场判断——有删除
> 原则（AGENTS.md：不留向后兼容/完成即删/删除优于标记）但无**判据层**
> （凭什么算过时/冗余/该删）。原则只答"该删就删"，判据答"怎么判断这个
> 具体东西该删"。无显式判据 → 该删不敢删（堆积膨胀）或标准漂移（删错
> 丢信息）。本设计沉淀判据表，作为删除动作的判定标准（先证后删）。

- **先证后删**：每条删除必须能指出命中哪条判据 + 证据（grep 零引用 /
  diff 等价 / 权威源存在 / 目标不存在）。说不出判据的删除不做。
- **删除优于标记**（继承 AGENTS）：不搞 deprecated/待清理挂着，过时就删。
- **能机器判的进门禁，不能的进清单**：判据是人工/模型清单；已机器化的
  只 D1（Doc: 引用已删目标）。不新增自动检查（误报面需先评估）。

### 代码删除判据

| # | 判据 | 证据 | 本次案例 |
|---|------|------|---------|
| A1 | 无引用死代码 | grep 零调用/零导入 | — |
| A2 | 双实现（功能重复） | 另一处等价或超集（diff） | `linter/cli.py`（main.py `_cmd_lint` 超集） |
| A3 | 决策已变的过时实现 | git log + ADR/落档 | `config_reference.md`（config.get 旧约定被 declare_cfg 取代） |
| A4 | 归属错 → **移动非删** | 目录职责表 | `analyzer/check_test.py`（测试设施在生产包 → tests/） |
| A5 | 结构不一致（编号/形态） | 与同类目录形态对比 | verilog 根文件 vs 主题目录 |

### 注释/docstring 删除判据

| # | 判据 | 证据 | 本次案例 |
|---|------|------|---------|
| B1 | 零信息增量（复述代码/空话） | 删除后信息零损失 | "引擎模块"式空话 docstring |
| B2 | 与权威源重复（清单/罗列） | 权威源存在（api.md/架构文档） | __init__.py 模块清单 vs api.md |
| B3 | 引用已删目标（过时事实） | 目标不存在（D1 门禁可抓） | — |
| B4 | 编辑残留（双 docstring/路径注释） | 结构异常（连续两个 docstring） | lexer/parser 双 docstring 叠加 |
| B5 | 过时注记（待补已补/路径已变） | 注记所指状态已变化 | "机制文档待补"（文档已存在）、transform 的 ext/_components 旧路径 |

### 文档删除判据

| # | 判据 | 证据 | 本次案例 |
|---|------|------|---------|
| C1 | 一次性计划已完成 | docs/README 纪律（成果入 CHANGELOG） | `e2e_real_projects.md`（real 语料 9 文件已就位） |
| C2 | 与代码漂移且无维护 | D3/D4 门禁辅助 + 内容对照 | `case_catalog.md`（内容停在 2026-08-26） |
| C3 | 与权威文档重复 | 单一权威源原则 | — |
| C4 | 版权/外部分发风险 | MANIFEST 排除先例 | `ieee1364_2005_annex_a.md`（IEEE 版权） |

### 反判据（不是删除理由——防误删）

| # | 反判据 | 理由 |
|---|--------|------|
| X1 | "看起来没用"（无证据） | 违反先证后删 |
| X2 | 历史调研/决策记录（references.md/ADR） | 落档纪律：git log 无法承载"为什么" |
| X3 | 个人思考沉淀 | 分层纪律：不对齐不套删除约定 |
| X4 | CHANGELOG 历史条目 | 发布记录不可篡改 |

### 使用方式

删除动作前对照判据表：命中 A/B/C 某条 → 说明证据 → 删；命中 X 某条 →
不删（或先落档再议）。清理类任务收尾时用本表复盘"本次删除都命中哪些
判据"，未命中的删除回滚或补证据——与"测试门禁 + 测后决策"同构。

**references.md 负重治理（2026-09-02 用户发起，治理设计）**

> 背景：references.md 2851 行，实际混合 5 类内容——①外部项目调研
> （本分，~1900 行）②机制研判/设计（~600 行，本属 ADR/架构文档）③执行
> 记录/修复落档（结果已进代码+测试+CHANGELOG）④规则行为预期（由测试
> 断言承载）⑤跨文件索引/调用点（代码 Doc: 引用）。根因：AGENTS.md
> "调研/研判/设计结论落 references.md（或 ADR/架构文档）"的"或"给
> 了最短路径（append 零成本 vs 建 ADR 有成本）→ 路径依赖导致分层失效。
> 定位：**收窄 references.md = 外部项目调研**（docs/README 原定位）；
> 其余类别落档路径在 AGENTS.md 明确化分流。

- **处置（用户拍板：堵新增 + 迁出设计类）**：
  1. **堵新增**：AGENTS.md 落档指引改为明确分流——调研→references.md；
     设计/研判→decisions/（ADR）或架构文档；执行结果/修复→CHANGELOG +
     测试断言，不进 references。删除判据表补"新内容落档前先判类别"。
  2. **迁出设计类**（②约 600 行）：增量解析设计思考（→ P3 相关 ADR 或
     架构文档）、删除判据（→ 独立判据文档或 ADR）、注入 vs 替换研判、
     用户标定打包研判、命名规则配置面设计、多后端输出设计（→ 对应
     架构文档/ROADMAP 详案）。
  3. **执行记录类**（③④）：按删除判据 C1/B5 压缩为小结或删除（结果
     已在测试/CHANGELOG），保留"为什么/推翻了什么"结论层。
- **同步面**：迁出后更新代码 Doc: 头、MODEL_INDEX、docs/README 索引、
  ROADMAP/TODO 回指；references.md 内互相引用锚点；删除判据 X2 措辞
  （references.md 仍不可删——它是调研落档处，但不再是设计落档处）。
- **验证**：两门禁绿 + 全量测试；迁移后 references.md 章节数/行数下降
  可量化（治理成效 = 行数回落 + 设计类章节归位）。



