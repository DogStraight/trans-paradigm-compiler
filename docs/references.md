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
| [Ohm](https://github.com/ohmjs/ohm) | 概念参考 | JS PEG + 语义操作分离 + 语法 OO 扩展 + 在线可视化编辑器 |
| [DHParser](https://gitlab.lrz.de/badw-it/DHParser) | 概念参考 | 完整 left-recursion 支持、测试驱动语法开发、声明式 AST 变换；错误恢复方案不同（反向解析器 vs post-mortem） |
| [Veryl](https://github.com/veryl-lang/veryl) | 设计参考 | SystemVerilog 现代超集 HDL（Rust，1026★，2022 起活跃）：语法简化 + 可综合保证 + 类型化 clock/reset + 转译保真——HDL 语法设计的直接参照（详见深调研） |

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
    注释，`analyzer/check_test.py::run_comment_driven` 运行检查后断言命中集合
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
| 文档生成 | mdgen 自动拼 MANUAL.md（13339 行） | MODEL_INDEX + case_catalog（手工维护） |
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
    文档生成可观察——tpc 的 MODEL_INDEX/case_catalog 是手工维护，若规则量增长到
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
- **优先级**：低于 C 语言包——当前仅 verilog 一个语言包要打包，硬编码还能撑；
  触发条件 = C 核心基线立项（多语言共存）或出现"非 verilog 打包"需求
