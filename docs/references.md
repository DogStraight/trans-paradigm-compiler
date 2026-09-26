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
| [ISO C99 标准文法](https://port70.net/~nsz/c/c99/n1256.html)（n1256，WG14 草案） | 设计参考 | C 包的**权威依据**：左递归的 `postfix-expression` 六形态（§6.5.2）、`integer-suffix`/`floating-suffix`（§6.4.4.1）、说明符分层（§6.7.1–6.7.4）——凡"C 到底怎么规定"的问题先查标准再决定取舍（详见深调研「C 语言文法参照」） |
| [tree-sitter-c](https://github.com/tree-sitter/tree-sitter-c)（grammar.js） | 设计参考 | 生产级 C 文法（GLR）：后缀**各自成规则 + 显式优先级**（SUBSCRIPT 17 / FIELD 16 / CALL 15 > UNARY 14）、`number_literal` 后缀按**字符类宽进**、`case_statement` **吸收**后续语句、前缀/后缀自增按位置区分——C 包三处取舍的直接参照（详见深调研「C 语言文法参照」） |

| 宏处理机制对照（[Lean 4](https://github.com/leanprover/lean4) / [Clang](https://github.com/llvm/llvm-project) / Verible / GLR） | 深度参考 | 结构宏进树（Lean syntax + macro scope 卫生）/ 编辑/格式化不展开宏 + raw 进 CST（Verible）/ 全展开 + 双位置 + 旁路记录表（Clang）——宏体入树（ADR-0016）的机制输入（详见深调研） |

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
| [LLVM](https://llvm.org/) | 深度参考 | 中段治理范本：New PassManager 管线字符串声明 + AnalysisManager 按需缓存/失效传播 + IR verifier 结构自检（详见深调研） |
| [GCC](https://gcc.gnu.org/) | 深度参考 | 中段治理另一范式：passes.def 静态声明序 + opt_pass 前置属性契约 + verify 固定收尾 + -fdump-* 可视化（详见深调研） |
| [jam](https://github.com/raphamorim/jam) | 深度参考 | 新系统语言全栈编译器（Rust）：flat AST → typed JIR（+ verifier）→ LLVM；`--emit-*` 冻结转储做重写期逐字节 oracle；typed IR + 机械 lowering 的分工（详见深调研） |

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

### 开发期工具链（审查/流程；非 tpc 设计来源，供"本体开发怎么做"参照）

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [Bifrost](https://github.com/BrokkAi/bifrost) | 设计参考 | Brokk 的多语言静态分析工具箱（Rust，Apache-2.0）：统一 IR + RQL 结构查询 + **显式证明层级**（proven/unproven）+ CLI/MCP/LSP/Python 四面；本仓用作外部审查与"换裁判"（规程 `policy/bifrost_audit.md`，自带 slopcop 诊断族） |
| [SlopCop](https://slopcop.brokk.ai) | 概念参考 | Brokk 的托管审计服务（specialist agent + 静态分析 → 案件报告 + 可复制为 prompt 的建议）；其实现在 Bifrost 的 `slopcop` 工具集里本地可跑，故不引入托管面（详见调研节） |
| [Spec Kit](https://github.com/github/spec-kit) | 设计参考 | GitHub 的 SDD 流程工具包（★137k，MIT，agent skills 形态）：本仓**只选择性借范式**（先成因后动手 / 收尾结论分级 / constitution 只用已成立原则），不引入 `.specify/` 目录与模板资产（详见调研节） |

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
  - 💡 政策即 CI：policy/ 把 ascii 规范、异常规范、架构检查做成自动门禁（tpc 有硬约束 AGENTS.md + lint recall 门禁，可借鉴"把约定变成检查器"的做法）
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

### 知名编译器中段治理机制（LLVM + GCC，2026-09-08 深调研，ADR-0015 前置）

> 调研动因：ADR-0015（中段治理方向：时点管线完整化 + 中间产物可视化 + pass 契约
> 校验）的抽象化输入。只聚焦**治理机制**（pass 时点/依赖声明、中间产物机械校验、
> 可观察性、分析缓存），不采 IR 语法本身。采集：agent-reach（github/web）+ 源码检索。

#### LLVM — New PassManager / AnalysisManager / IR verifier

- 定位：中段治理"可编排优先"的范本——pass 是 CRTP mixin（无继承接口），管线用字符串
  名声明（`opt -passes='function(foo,loop(bar)),module(baz)'`，
  `PassBuilder::parsePassPipeline`），`require<analysis>` 可强制预计算。

**机制要点（对 ADR-0015 三个抽象）：**

| 治理问题 | LLVM 机制 | 关键设计 |
|---|---|---|
| 时点/依赖声明 | AnalysisKey + `AM.getResult<A>()`（运行时按需拉取）；`PreservedAnalyses` 声明"破坏/保留哪些分析" | 依赖运行时按需，非静态表；失效靠 pass 返回的 PA 沿依赖链传播 |
| 分析缓存 | AnalysisManager 以 IR 单元地址为 key 缓存；invalidate() 传递失效 | "避免重复分析"是 AM 存在的首要理由；内层 pass 不允许触发外层分析（防二次方） |
| 产物机械校验 | `verifyModule/verifyFunction`（IR verifier，自建 DT 不信任缓存）；`-verify-each` 走 instrumentation 回调（非真 pass）每 pass 后验，坏即报"after pass X" | 结构性自检是**可插拔环节**：输入/每 pass 后/管线结尾/调试期任意插（默认结尾 verify，`-disable-verify` 逃生门） |
| 可观察性 | -print-before/after-all（断点式全量）、-print-changed（只报变化 diff，低噪声首选）、-debug-pass-manager（调度轨迹）、-time-passes；全挂 PassInstrumentationCallbacks | 可视化 = **事件总线式 instrumentation**，pass 代码零感知；默认低噪声、可按 pass 过滤 |

**对 ADR-0015 可参考点：**
- 时点分"粒度（module→function→loop）× 位置"两维建模；管线用声明式名字序列（可平移 TOML 把 pass 顺序当数据写）
- pass 契约 = "影响面声明 + 校验比对"（pass 声明破坏了哪些分析 → 校验环节比对实际改动）
- verifier 要能独立自证（自算所需 DT），坏时点校验器不能建立在"缓存一定准"假设上
- 可视化做"每时点发回调"的观察者机制，不掺 pass 本体（事件总线）

#### GCC — passes.def 静态声明 / opt_pass 契约 / verify 固定收尾 + -fdump

- 定位：中段治理"可观测/可校验优先"的范本——pass 顺序是**编译期数据**（passes.def 宏
  清单 + sub 嵌套，gen-pass-instances.awk 展开），运行时只做 gate 动态裁剪（每函数判定，
  `-Og/-O0` 选不同子序列）。

**机制要点：**

| 治理问题 | GCC 机制 | 关键设计 |
|---|---|---|
| 时点/依赖声明 | passes.def 声明序（数据非代码）；opt_pass 声明 properties_required/provided/destroyed；gate() 每函数动态（失败连带跳过整组） | 依赖不显式声明 = "声明序 + 前置属性断言"；执行前 verify_curr_properties 断言、执行后按 provided/destroyed 记账 |
| 产物机械校验 | `TODO_verify_il` 无条件注入每个 pass 收尾 → 按 curr_properties 分派 verify_gimple/verify_ssa/verify_flow_info/verify_loop_structure；--enable-checking/-fchecking 门控 | verifier 是 **pass manager 固定收尾环节**（非 pass 各自的事）；校验内容由"声称输出的 IL 属性"自动决定；成本显式门控（默认关） |
| 可观察性 | -fdump-passes（列全部 pass + 开关态，是启用开关的发现入口）；dump 文件 `源.编号.相位.pass名`；pass 名既是 dump 名又是 CLI 开关名；star 名静默；-fdump-noaddr/unnumbered 可比性 | dump 生命周期挂 manager 骨架（开→逐函数写→关），pass 只 dump_printf——可视化是横切机制；30 年演化的自带调试基础设施 |
| 多遍 | 同 pass 类多实例（构造实参区分，passes.def 重复出现），实例号进 dump/禁用接口（-fdisable-tree-ccp1） | "类 + 构造参数 + 实例编号"，精确定位"第几次" |

**对 ADR-0015 可参考点：**
- "可配置"可以是"数据化声明 + 显式契约"，不必是"运行时可重排"——静态表也能支撑极强可视化/校验（对照 LLVM 编排优先）
- pass 声明前置属性/输出属性 → manager 前置断言 + 后置记账，比事后 verify 更早暴露次序错（契约前置）
- dump 启用从"列出"来（-fdump-passes 先列后拼开关）→ tpc 可做"列出全部时点+状态"命令

#### 两相对照（编排优先 vs 可观测/可校验优先）

| 维度 | LLVM | GCC |
|---|---|---|
| 时点声明 | 运行时字符串管线（可编排） | 编译期静态表 + gate 裁剪（可枚举） |
| 依赖 | AnalysisKey 运行时按需 + PreservedAnalyses 失效 | 声明序 + 前置属性断言 |
| 校验 | verifier 可插任意时点（instrumentation） | verify 固定收尾（manager 骨架注入） |
| 可视化 | -print-*/debug-pass-manager/timing 事件回调 | -fdump-* pass 绑定 + 可比性设施（去地址/diff） |
| 对 tpc 侧重 | 可编排 + 低耦合声明（TOML 管线 + 影响面契约 + 事件式可视化） | 可观测 + 契约（静态声明序 + 前置属性记账 + 列出式 dump 入口） |

**收敛（ADR-0015 抽象化输入）：**
1. 时点 = "粒度 × 位置"两维（承接时点线模型；GCC 三级 list+sub 嵌套可借鉴）
2. 校验做"可选、可插、按声明自动选验什么"——LLVM 任意时点插 + GCC 按 IL 属性自动分派
   （tpc 对应"按产物契约自动选校验器"；成本门控 + 逃生门，对齐粒度自选）
3. 可视化做事件回调 + 低噪声 diff + 列出式入口（-fdump-passes 模式）——不改 pass 本体
4. 缓存按产物单元 + 失效传播（AnalysisManager 模型），但 verifier 不依赖缓存（独立自证）

### 宏处理机制对照（Lean 4 / Verible / Clang / GLR，2026-09-11 深调研，ADR-0016 前置）

> 调研动因：ADR-0016（宏体入树——raw 源区间权威 + 展开分级投影 + 对应层）的机制
> 输入。只聚焦**宏在管线中的处理位置与信息保全**（宏进不进 AST、位置/对应关系如何
> 存、展开时机），不采其语法/类型系统本身。

#### Lean 4（C++ 自举 + Lean 自写 elaborator）— syntax 树级结构宏

- `Macro = Syntax → MacroM Syntax`：宏是 **syntax 树节点**（带 kind），parser 只圈边界，
  内容理解延迟到 elaboration 展开
- 卫生 = macro scope（`MacroScope := Nat`，进宏作用域 bump；引号引入标识符 mangle 上
  scope，elaboration 期再解析防捕获）
- 位置全程携带：`Syntax.ident` 带 SourceInfo（original / synthetic / canonical）
- 增量：非增量 parser，是命令级 snapshot 缓存（`MacroExpandedSnapshot`）+ 文件级 olean
  缓存；纪律 "Limit ref variability"
- 💡 启示：结构宏天然 syntax 进树，parser 不解析宏体只圈边界

#### Verible（C++，Google）— 同生态最接近：格式化不展开宏，raw 进 CST

- 格式化模式**不展开宏**：`filter_branches = false`，注释 "we want to emit all tokens"
- 宏调用 raw 进 CST（`kMacroCall` 节点）；宏参数/定义体是 **unlexed 文本**
  （`PP_define_body`、lexer `PP_MACRO_FORMALS` 状态：原文累积 + 括号平衡，不拆 token）
- 格式化对宏只处理**边界**（`MacroCallReshaper` 换行/缩进/间距）；`uvm_begin/end` 宏块缩进
- 语义检查对宏内 = 递归 lex raw 文本（`RecursiveLexText`）
- 🔥 启示：Verilog formatter "宏 raw 当渲染单元 + 只格式化边界" 成熟可行——**渲染权威
  = raw**

#### Clang（C++）— 全展开 + 双位置 + 旁路记录表（文本宏专用架构）

- **全展开**（语义需要）；Token 的 SourceLocation 编码**双位置**：spelling location（字符
  原始出处）+ expansion location（宏展开点）——"capturing both the ultimate instantiation
  point and the source of the original character data"
- **PreprocessingRecord**（PPCallbacks 子类）：预处理时回调记录实体流——MacroExpansion
  （SourceRange + →定义回链）/ MacroDefinitionRecord / InclusionDirective；支持"源范围 →
  命中的展开"反向查询；可序列化进 PCH/AST
- Token 本身是"源位置 + 长度"指向 source buffer——**raw 从不复制存储，按位置切片**
- 🔥 启示：**不存两棵树**，用"展开主结构 + 旁路事件表（源位置锚定）"拿到全部信息；
  源位置是唯一真源，raw 需要时从源缓冲切

#### GLR 解析森林（Elkhound / SDF3）— 歧义路径保留后期裁剪

- "歧义路径保留后期裁剪"处理的是**语法歧义**（packed parse forest），**非宏**；与宏双路
  "形似"（都保留多份）但机制不同——仅思想来源
- 📌 路线观察：不适用于 tpc 宏场景（tpc 宏是文本替换语义，非歧义保留）

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

### C 语言文法参照（ISO C99 §6.5.2 + Clang + tree-sitter-c，2026-09-25 深调研）

C 包从"声明面"走到"表达式面"时遇到的三个形状问题（后缀链、字面量后缀、case 缩进），
都能在标准与成熟实现里找到依据或对照，故单列一节。

- 定位：**标准**是权威依据（n1256 = C99+TC3 草案，WG14 官方站点镜像）；**Clang** 是
  手写递归下降的工业级代表（与 tpc 同族实现路径）；**tree-sitter-c** 是 GLR 路线的
  生成式文法代表（与 tpc 异构，正好当"另一种解法"的对照）

**1. 后缀链（postfix-expression）**

| 来源 | 形态 |
|---|---|
| ISO C99 §6.5.2 | **左递归**六形态：`postfix-expression` 可再由 `[expr]` / `(args)` / `.id` / `->id` / `++` / `--` 扩展 |
| Clang `ParsePostfixExpressionSuffix`（[ParseExpr.cpp](https://chromium.googlesource.com/native_client/nacl-llvm-project-v10/+/244b96ba0a047185ae82f5dc8903ea0756b18b9f/clang/lib/Parse/ParseExpr.cpp)） | 手写路径：**先解析 leading part，再循环吃后缀**——不做左递归 |
| tree-sitter-c | 各后缀**独立成规则**，base 为 `$.expression`，靠 `prec(SUBSCRIPT 17 / FIELD 16 / CALL 15)` + GLR 消歧 |
| tpc（本包） | 同 Clang 的形态：`PostfixExpr{base, suffixes}` = 原子 + 后缀+；后缀链长度不受限 |

- 🔥 **借鉴（已落地）**：Clang 的"leading part + 后缀循环"就是 tpc 能表达的形态
  （递归下降表达不了左递归），实现见 `grammar/c/00_expressions.toml::PostfixExpr`；
  旧实现是三个**单级**规则（`CallExpr` 的 base 只能 `@Identifier`），故 `a.b.c` /
  `f(x)[i]` / `p->a[i]` / `(*fp)(x)` 都不支持——已按本节参照改掉并转正向用例。
- 📌 **不实现**：GLR/优先级消歧（tree-sitter 路线）。tpc 走"最长匹配 + FOLLOW 硬检查"，
  取舍是**声明面更简单**（不需要写优先级数字）但**要自己排形态**（见包内注释的
  FOLLOW/环约束）。

**2. 字面量后缀（`integer-suffix` / `floating-suffix`）**

| 来源 | 形态 |
|---|---|
| ISO C99 §6.4.4.1 | 后缀是**有限组合**（`u`/`U` + `l`/`L`/`ll`/`LL`），合法组合有明确枚举 |
| tree-sitter-c `number_literal` | 实现上按**字符类宽进**：`/[uUlLwWfFbBdD]*/`（还含 MS 扩展）——组合合法性不在这里判 |
| tpc（本包） | 同 tree-sitter 的选择：`[[number.based]] suffix = { chars, max }` 给"可选字符集 + 长度上限"，**组合合法性归约束层** |

- 🔥 **借鉴（已落地）**：tree-sitter 的做法印证了"词法层宽进、约束层收紧"对本问题是
  成熟解（C 的 pp-number 本就宽进）；实现见 `lexer/number_runner.py::_consume_suffix`。
- 💡 **实现差异（有意）**：tpc 把后缀做成 **DFA 之后的声明式尾段**而不是 DFA 边——
  引擎的字符→类别映射是全局的，`f`/`F` 已是十六进制 digit 类别，按类别加边会与 hex
  值自环撞键（判据 `0x1FF` 钉在 `tests/engine/lexer/test_number_suffix.py`）。

**3. `case` 体缩进（未闭环，参照在此）**

| 来源 | 形态 |
|---|---|
| ISO C99 §6.8.1 | `labeled-statement: case constant-expression : statement`——label 只拥有**一条**语句（`case 0: a; b;` 的 `b` 不属于 label） |
| tree-sitter-c `case_statement` | **吸收**后续语句：`prec.right(seq(choice('case expr','default'), ':', repeat(choice($._non_case_statement, $.declaration, ...))))` |

- 💡 **启发（未采纳，记档）**：tree-sitter 用"label 吸收后续语句"换来缩进自然
  （body 嵌套即缩进），代价是 AST 语义偏离标准（语句被挂到 label 下）。tpc 当前选
  **标准形状**（label 是独立语句节点），故渲染端缺一级缩进——已记在
  `docs/gaps/gap-language-pack-scope.md` §C（要修需渲染端"标签后同级子节点多缩进一级"
  的能力，或在包侧改用吸收形态）。两条路都记着，等有真实需求时再取舍。

**4. 前后缀自增的节点形态（旁证）**

- tree-sitter-c `update_expression` = `choice(seq(op, arg), seq(arg, op))`：**同一节点名、
  按位置区分**前后缀——与 tpc 的 `UnaryOp{position}` + `when` 分发布局同构 ✓（tpc 侧
  `when` 原语的动机即"同节点名两形态"，见 `renderer/renderer_architecture.md`）。

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

### 静态检查器功能调研（2026-08-22，语义检查插槽前置调研）

> 原 `docs/references/static_checkers_survey.md`（2026-09-04 并入本文件，消除
> references/ 目录与 references.md 同名）。性质：设计来源记录（references）——
> 语义检查插槽（`analyzer/semantic_checks.md`）的前置调研，决定 tpc 语义检查系统
> "做什么（功能矩阵）"与"怎么学（规则架构）"。后续扩展见本文件「Verilog
> 静态检查工具群研判」「主流 lint 机制调研（P1.10 三路）」「svlint 深调研」。
> 规则引擎部分经 web 检索核实，来源 URL 附各节末。

#### 一、Verilog/HDL 静态检查器功能矩阵

| 类别 | Verilator | Verible | SVLint | Slang/iverilog | SpyGlass/Questa |
|---|---|---|---|---|---|
| 宽度/截断/扩展 | ✅ WIDTH（elaboration 后按具体参数值查） | ❌ | ⚠️ 部分 | ⚠️ 诊断级 | ✅ 全套 |
| 未连接信号 | ✅ UNDRIVEN | ❌ | ❌ | ❌ | ✅ |
| 未使用信号 | ✅ UNUSED/UNUSEDSIGNAL | ❌ | ❌ | ❌ | ✅ |
| 推断锁存器/组合环 | ✅ LATCH/UNOPTFLAT | ❌ | ❌ | ❌ | ✅ |
| case 完整性 | ✅ CASEINCOMPLETE/CASEOVERLAP | ❌ | ❌ | ❌ | ✅ |
| 隐式声明 | ✅ IMPLICIT | ❌ | ⚠️ | ⚠️ | ✅ |
| 命名/风格 | ⚠️ 少量 | ✅ 主场（module-filenames、line-length、no-tabs、always-comb/ff 等） | ⚠️ | ❌ | ⚠️ |
| CDC/跨时钟 | ❌ | ❌ | ❌ | ❌ | ✅ 主场 |
| 复位/DFT/功耗 | ❌ | ❌ | ❌ | ❌ | ✅ |
| 可综合性 | ⚠️ 部分 | ❌ | ❌ | ❌ | ✅ |
| **配置化参数敏感性** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **链级溯源报告** | ❌ 单点 | ❌ | ❌ | ❌ | ⚠️ 层级化，不跨语句链 |

**各工具要点**（HDL 工具细节的扩展见下「Verilog 静态检查工具群研判」+「主流
lint 机制调研」）：Verilator `--lint-only` 的 W 系列警告最接近"真静态检查"，
宽度检查在 elaboration 后拿**具体参数值**查截断（`DATA_W=16` 时 `16'hFFFF`
合法）——结构上无"配置可能变"概念；Verible 是风格/结构规则主场（规则 + 抑制
`// verilog_lint: waive rule-name`）；SVLint 语法/结构为主（`.svlint.toml`
实例：OpenTitan/ibex）；Slang/Icarus 是编译器前端诊断；SpyGlass/Questa 商业
天花板（lint/CDC/RDC/Reset/DFT/power 全套），无跨语句链溯源。**两行独有洞察**：
全工具无"配置化参数敏感性"与"链级溯源"——正是 tpc 语义检查差异化（P2/P3
声明式规则表 + WC001 赋值链）的支撑。

来源：Verilator warnings 文档 / [Verible verilog-lint](https://chipsalliance.github.io/verible/verilog_lint.html) +
default_rules.h / [SVLint crate](https://docs.rs/crate/svlint/0.4.14) + OpenTitan
`.svlint.toml` / VC SpyGlass CDC、RDC 数据手册。

#### 二、可定制规则引擎架构对比（Semgrep / CodeQL / ESLint / clang-tidy / Ruff）

> 调研目标：tpc 要"规则=配置/数据、复杂检查=脚本"——业界五个代表性系统怎么设计。

**1. Semgrep — 纯声明式 YAML 规则引擎**：纯配置（YAML `rules:` 列表，无用户
脚本，复杂逻辑靠声明式算子组合）。Schema：`id`/`message`（`$VAR` 元变量
插值）/`severity`/`languages`/`patterns`/`fix`/`metadata`（cwe/owasp/
category）/`paths`/`mode`（search/taint/join）。匹配：AST 模式匹配（写目标
语言代码片段），元变量 `$X`/`$...ARGS`/省略号 + 布尔算子
`pattern-either/-inside/-not/-regex` + 元变量约束；`mode: taint` 数据流
（Pro 给路径链）。抑制：`// nosemgrep[: rule-id]`/文件级/`paths.exclude`/
不选即关。扩展：Registry 规则包（`--config p/...`，规则=YAML 文件）。
测试：`semgrep test` 文件内 `// ruleid:`/`// ok:` 注释驱动断言（零代码）。
报告：行/列/命中片段/插值 message + `--json`/SARIF/`--autofix`。

**2. CodeQL — 声明式逻辑查询语言（数据流/溯源天花板）**：写 QL（Datalog+OO），
`.ql` 即规则（`from/where/select` 查关系数据库：AST/符号表/CFG/数据流/SSA）。
Schema 元数据在注释头：`@kind`（problem/path-problem/alert）/`@severity`/
`@precision`——path-problem 多 source/sink 列，报告器据此画数据流路径。
匹配：谓词/量词/递归库实体；数据流继承 `TaintTracking::Configuration` 覆写
source/sink/sanitizer/step，库完成跨过程/跨文件路径计算。抑制：查询套件
选择 + Code Scanning inline `// codeql[<id>]`。测试：`codeql test run` 对
`.expected` 快照。报告：SARIF，**path-problem 完整 source→中间步→sink 路径**
（五者中溯源最强）。

**3. ESLint — 规则即 JS 代码（visitor + 数据配置的双层模型）**：双层——规则 =
JS 模块（`meta` + `create(context)` 返回 AST visitor）；配置 = 数据
（`rules: {"id": ["error", options]}`）。Schema（meta）：`type`/`docs`
（recommended）/`schema`（JSON Schema 校验 options，fail-fast）/`messages`
（模板字典 `{{placeholder}}`，messageId+data 插值）/`fixable`/
`defaultOptions`——**严重度不在规则里而在配置中**（off/warn/error）。
匹配：AST visitor + esquery 选择器 + scope/类型 API。抑制：`eslint-disable*`
族 + overrides/ignorePatterns。扩展：npm 插件包。测试：**RuleTester**
（valid/invalid 用例 + 期望诊断逐字段断言：messageId/type/line/data/fix），
事实标准。报告：`context.report`；无内置数据流。

**4. clang-tidy — 规则=编译器内 C++ 代码，配置=YAML 文件**：check 编译进
二进制（用户一般不现场写）；`.clang-tidy` YAML（`Checks`/`WarningsAsErrors`/
`HeaderFilterRegex`/`CheckOptions`）。命名空间前缀即分类（bugprone-/
readability-/modernize-/...）。匹配：C++ AST matcher（`callExpr(...)`）+ check
回调语义判断。抑制：`// NOLINT`/`NOLINT(check-name)`/`NOLINTNEXTLINE`/
`NOLINTBEGIN...END`。扩展：无市场（`ClangTidyModuleRegistry` 自建）。
测试：lit 测试（`// CHECK-NOTES:/CHECK-MESSAGES:` 期望注释）。报告：clang
诊断格式 + notes + fix-it；单翻译单元，无跨过程数据流路径。

**5. Ruff — 配置驱动的内置规则 + Rust 插件生态（对比参考）**：纯配置（TOML）
启用，规则 Rust 编译进二进制。Schema：code（F401）/name/category/fixable/
preview；配置 `lint.select`/`ignore`/`extend-select`/**`per-file-ignores`**
（glob → 规则列表）/`exclude`。抑制：`# noqa[: F401]`/`# ruff: noqa`/
`per-file-ignores`。扩展：Rust 插件 API（0.9+，早期）。测试：insta snapshot。
报告：诊断 code+位置，`--fix`；定位快速 lint。

**对比表**：

| 维度 | Semgrep | CodeQL | ESLint | clang-tidy | Ruff |
|---|---|---|---|---|---|
| 声明方式 | 纯配置 YAML | 声明式查询语言 QL | 双层：规则=JS，配置=数据 | 规则=C++ 编译期，启用=配置 | 规则=Rust 编译期，启用=TOML |
| 复杂判定 | 声明式算子组合 | 谓词/数据流库 | visitor + 自研分析 | AST matcher + 回调 | 内置规则（插件 API） |
| 测试框架 | 注释驱动 ruleid/ok | `.expected` 快照 | RuleTester 逐字段断言 | lit CHECK-* 注释 | snapshot |
| 报告溯源 | 单点（Pro 路径） | path-problem 完整链 | 单点 | notes | 单点 |
| 抑制 | nosemgrep 注释/配置 | 套件选择 + inline | disable 注释族 | NOLINT 注释族 | noqa 注释/per-file |

（注：本调研的 L1 声明式规则表、注释驱动测试、per_file 豁免分别对位
tpc `[[checks]]` schema / `tests/_check_test.py` / `config` per_file——见
`analyzer/semantic_checks.md`。）

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

#### 宏/指令卫生族 + 排版族归属补充调研（2026-09-11，T1 收尾 / T2 前置）

- 背景：T1 重合核心集第 10 项（宏/指令卫生）与 T2 零成本语法层候选，都卡在
  "落 linter 还是 check 链"这一前置决策上。存量调研只有规则清单，缺**精确判定
  边界**与**分层依据**，本补充定向补齐（来源：svlint MANUAL 全量规则说明、
  Verilator warnings 全表）。

**一、宏/指令卫生：三家精确判定**

| 工具 | 规则 | 判定 | 关键边界 |
|---|---|---|---|
| svlint | `default_nettype_none` | 文件须出现 `` `default_nettype none `` | 单文件、只看"是否声明" |
| svlint | `default_nettype_wire_at_end` | **文件末尾生效值须为 `wire`** | 单文件末尾状态；防跨文件泄漏 |
| Verilator | `REDEFMACRO` | 宏重定义**且值不同**才报 | 同值重定义不报；跨文件与 `+define+` 参与 |
| Verilator | `DEFOVERRIDE` | 代码 define 覆盖命令行 define | 与 REDEFMACRO **分码**，不合并 |
| slang | `redef-macro` | 同类（重定义即报） | 未给"值相同"例外 |

- svlint MANUAL 自述：155 条语法规则里**只有 4 条 filename 匹配 + 1 条文件内状态
  （`default_nettype_wire_at_end`）需要文件级上下文**——印证这两条属"消费文件
  级状态"而非 pattern/符号检查。
- 落点判断（侦察 tpc 实现后修正）：均需**指令级/宏表状态**，pattern 与符号 kind
  都表达不了。tpc 的对应层是 **linter**——它已在解析前消费指令与宏表（`scanner.py`
  调 `scan_directives`/`expand_tokens`），且 `checkers/macro_token.py` 已有同族检查
  （undefined-macro）。tpc linter 相当于 svlint textrules + syntaxrules 的 token 级
  并集，故**不需要另起 check 链 handler**。
- ⚠ 边界取舍：`default_nettype` 跨文件泄漏的完整语义需"编译单元"概念，svlint 也
  只做单文件末尾检查 → tpc 同样只做单文件，跨文件留 gap 记录。

**二、排版/空格族：svlint 自身给出的分层（T2 归属依据）**

- svlint MANUAL 明确两段式：**`textrules` 在任何解析之前**（文件当任意文本，
  不要求是合法 SV）；**`syntaxrules` 走 AST 事件遍历**。这个分界可直接映射到 tpc
  的 linter（解析前/token 级）与 check 链（AST/符号级）。
- 候选规则归属对照：

| 候选 | svlint 归属 | Verible 机制层 | tpc 落点建议 |
|---|---|---|---|
| 行长（line-length） | `textrules`（`style_textwidth`，默认 80） | 行级 | **linter**（原文行级，零解析依赖） |
| 尾随空格 | `textrules` | 文本结构级 | **linter** |
| 分号前空格 / 指令缩进 / 版权头 | `textrules` | 文本结构级 | **linter** |
| tab 字符 / 缩进倍数 | `syntaxrules`（`tab_character`/`style_indent`） | Token 级 | **linter**（token 含原文与位置） |
| 空格规范族（`style_keyword_*`/`style_operator_*`） | `syntaxrules` | Token 级 | **linter**（token 邻接关系） |

- 结论：**排版/空格族整体落 linter 层**——token 流已具备原文与位置，与 svlint 的
  "解析前"定位一致；check 链留给需符号表/文件级状态的规则（含宏卫生族）。
- 另注：Verible 的 `line-length`/`no-tabs`/`no-trailing-spaces` 属其"行级/Token 级"
  少数派（48 条 AST 规则之外），与上表判断一致。

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
  （指针化）——当时判为“个人项目暂不必要（文件仍在 ~100 行预算内），观察增长再动”；
  **2026-09-18 已执行**：AGENTS.md 138 → 57 行（协作范式迁 `policy/collaboration.md`、
  文档放置速查迁 `docs/README.md`、开发自查工具清单迁 `tools/README.md`、子系统表
  改为指向 `docs/engine_overview.md`）
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

#### slang-tidy 追查（2026-08-29，bin 里找不到？→ 官方从未打包）

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

#### slang-tidy 完成度源码级评估（2026-08-29，与对照组对比）

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

#### 不卫生宏体检测可行性（2026-08-29，原型验证 14/14）

- **背景**：checker 现为"一刀切全展开"（semantic=True 宏体替换，宏节点
  不入 AST）。原意图是带宏节点进 parse，但残缺片段宏（`= 1'b1`、
  `[3:0]`、`begin`/`end` 半截）会破坏语法边界让 parse 失败 → 只能全展开。
  设想：先做**宏体形态分类**（完整语法单元 vs 残缺片段），完整单元宏将来
  可保留为 MacroCall AST 节点，残缺宏维持原位展开。
- **方案：包装解析法 + 首 token 预过滤**（2026-08-29 原型实证）：
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

### jam（Rust）— 全栈系统语言编译器：flat AST → typed JIR → LLVM（2026-09-17 调研，agent-reach + GitHub 源码）

**定位**：Raphael Amorim 的个人语言项目（[jamlang.org](https://jamlang.org)，2025-11 起，
221★/7 fork，Apache-2.0 with LLVM Exceptions）。一门**新的静态类型系统语言**（mutable
value semantics、泛型、tagged union、comptime），自带编译器 + std 库 + LLVM 后端；
**Rust 重写自其 C++ 前身**（最后一个 C++ commit `4e66bc6`）。当前 v0.1 未发布、
issue/PR 关闭、README 声明 No AI Policy（贡献政策）。

**三端实现（源码级）**

| 端 | crate | 方案 |
|---|---|---|
| 前端 | `jam-syntax` | 手写 byte-level lexer（关键字直接 match 字节串）+ 数字字面量解析器 + **flat/tag-dispatched AST**（`ast_flat.rs`：打包节点数组 + `extra` 池存变长负载，按 `AstTag` 分派；`TypePool`/`StringPool` 驻留）+ 手写递归下降 parser（优先级爬升；语句/表达式入口细分，直接写共享池并报诊断） |
| 中端 | `jam-sema` | `astgen.rs`：AST → **JIR（typed flat IR）**，边降边做 definite-init/drop/exclusivity 检查与 comptime 求值；`analyzer.rs` + `abi.rs`：声明/类型/布局与 **C ABI 分类**（`classify_param`/`classify_return`，rustc 式 by-value-by-pointer 阈值）；`init_analysis.rs`：MVS 三规则（definite init / exclusivity / linear drop）；`drop_registry.rs`、`generics.rs`（按实例化克隆，每实例一个 LLVM 符号）、`module_resolver.rs`/`mangling.rs`；`jir_verify.rs`：**IR verifier**（结构 + def-before-use + 负载边界） |
| 后端 | `jam-sema::jir_codegen` + `jam-llvm` | `jir_codegen.rs` 自述“purely mechanical: no inference here”（`JirInst` → 几条 LLVM 指令）；`jam-llvm` = LLVM C API raw 绑定 + **C++ shim（`shim/jam_shim.cpp`）** 补新 PM 优化管线（作者记录：不接 shim 时 `--release` 只跑 codegen pass、IR 级 pass 全空，与 `-O0` 无区别）；target/opt/LTO/strip 走 `-C key=value`（对齐 rustc 的 CLI 形态） |
| 驱动 | `jam`（CLI） | `cli/run.rs`（单遍参数循环 + `-C` 解析）、`cli/emit.rs`（`--emit-tokens/ast/jir/ir` 文本转储） |

**管线**：`Source → Tokens → AST → AstGen → JIR → Codegen → LLVM IR`（`jir.rs` 头注）。

#### 对照：宏体入树（tpc 0.1.2 的核心问题）

jam **没有文本宏系统**（全仓检索 preprocessor/macro/#define 无命中；官网 reference 章节表
亦无预处理章节）——它的编译期能力是**语言内一等构造**，因此"宏体是文本、要再解析、
渲染要还原原文"这一整类问题在它那儿不存在：

| | jam | tpc（ADR-0017 路线） |
|---|---|---|
| 编译期机制 | `comp`（const/var/if/参数特化）+ `cfn`（编译期执行、把代码**发进调用者**）+ `@` 内建 | 文本宏（`` `define `` / 宏调用）由**外层预处理器**处理，引擎不承认宏语法 |
| "宏体"是什么 | **类型化 JIR 指令**（编译器自己造的节点，不是待解析文本） | 源文本片段（需重新走 lex/parse；或按 ADR-0017 由 linter 在展开后文本上检查） |
| 产出物定位 | jam 的产物是 IR/机器码 → 每个 JirInst 只带 `src_line` 供诊断用；**无需还原调用点原文** | tpc 的产物是**格式化后的源码文本** → 宏调用必须按原文输出（`MacroCall` 节点 + raw 源区间还原） |
| 死分支/常量 | `comp if` 死臂**从不 lower**、`comp const` 在使用点内联为常量值——没有"文本残留"要清理 | 展开后要保证渲染能逐字还原、位置可映射（条件编译还原是 P1.5 的难点） |

**实现细节（可借鉴的工程手法）**：`cfn` 体在 AstGen 期执行，执行时共享池被不可变借用
（`exec_block` 持借用）→ 调用者的 JIR **不能在执行中被改**，于是它们把编译期要产出的代码
**记录为纯数据**（`CfnEmitCmd`，如 `WriteBytes { fd, fmt, .. }` / `PrintLocal`），
**执行结束后再 replay 进调用者的 JIR**（`astgen.rs::RecordingCfnEmitter` + 实现
`comptime::CompEmitter` trait 的 `handle_at_call`；docstring 原文："intrinsics are RECORDED
as pure data during execution and REPLAYED into the caller's JIR after the borrows release"）。
产出指令经统一 `emit()` 入块，`src_line` 取当前节点行号 → 诊断仍指向宏生成处附近。

- 💡 **对本项目的启示（不照搬）**：两边的取舍由**产物形态**决定——产物是源码文本（tpc），
  就必须保留调用点原文与位置映射；产物是 IR（jam），"编译期生成"天然就是造节点。
  tpc 若要减少文本展开面，可考虑的不是"把 preprocessor 变成 typed IR"（那会要求语言有类型
  系统），而是**收窄需要原文还原的宏形态**（ADR-0017 已走一半：完整单元宏可入树、残缺片段
  维持展开）——判据仍是"渲染能否逐字还原"。
- 💡 **记录-重放（record-then-replay）** 是可复用模式：当"执行期不能改目标结构"（借用/锁/
  事务边界）时，把副作用记成纯数据、边界之外统一物化。tpc 的 postpass 链/单元产物通道
  （`note_produced` → `PassState.productions`）本质是同构的"执行期登记、边界后消费"。

**与 tpc 的对照**

| 维度 | jam | tpc |
|---|---|---|
| 定位 | 一门语言的**全栈**实现（语言设计 + 编译器 + std + FFI） | **语言无关的配置驱动前端管线**（语言是数据；不绑语言、不含后端/运行时） |
| 加语法 | 改 Rust 代码（lexer/parser/ast_flat/astgen/codegen 多点） | 改 TOML（`grammar/<lang>/`），引擎零语言知识（门禁守） |
| 中端 | typed IR（JIR）+ verifier + MVS 检查 + comptime 求值器 | 作用域/符号/浅语义 + 声明式检查（L1）+ postpass 链（时点契约化）；**无类型推导系统、无 IR**（接受项） |
| 后端 | LLVM IR（ABI 分类、opt/LTO/strip） | 无后端：renderer 出格式化文本；c4 演示 asm/渲染插件 |
| 验证 | **差分 oracle**：`--emit-*` 格式与 C++ 前身**逐字节一致**（`cpp-final` tag）+ Rust 单测 + `.jam` 语料 | 对拍（sv-parser/Verible/slang/svlint）+ 门禁体系（覆盖率/smoke/误报基线只许减/隔离巡检/门禁有效性）+ fuzz |
| 工具面 | 无 formatter/linter/LSP/增量（检索无命中，重心在编译正确性） | 差异化正在这里：格式化保真（双世界）+ 前置 token 级 lint（recall 31/31、0 误报）+ 可配置规范执行 |
| 治理 | 官网 reference 详尽 + 仓库根 `*_PLAN.md`（带 Zig/rustc 源码**文件与行号**对照的调研） | ADR / MODEL_INDEX / gaps / policy 分层 + 门禁脚本 |

**亮点（标注）**

- 🔥 **中间产物文本转储作为冻结 oracle**（`--emit-tokens/ast/jir/ir`，格式冻结到逐字节，
  重写期间对齐前身实现）：与 tpc 的“对拍验证”同构，但它把**转储格式本身**做成了有
  契约的对外接口。tpc 已有中间产物落盘（gen/ast/symbols/lex）+ trace JSON，缺的是
  “格式冻结 + 逐字节可比”的声明；做 P4 前端桥时这是最省事的回归手段。
- 🔥 **typed IR + 机械 lowering 的分工**：类型/ABI 决策全在前端完成，后端只做
  `JirInst → 指令`（明说 no inference）。对 tpc 的 P4.1（多后端）是可直接搬的结构：
  插件声明目标 → 前端产出类型化中间表示 → 后端机械翻译。
- 💡 **IR verifier 作为独立可测组件**（`jir_verify.rs`：结构 / def-before-use / 负载
  边界，返回诊断列表）：与 tpc 刚收编的“单元契约 / 时点可达性校验”同类——校验
  中间态合法性而非事后调错。tpc 可考虑给 AST/Doc IR 定一组结构不变量做 debug 校验。
- 💡 **comptime 求值器自带迭代上限**（`DEFAULT_ITER_CAP = 10_000`，超限报“可能死循环”）：
  tpc 若引入编译期求值（宏/参数折叠），这是必备护栏形态。
- 📌 **MVS / 参数模式 / 线性 drop**（Hylo/Swift 谱系，论文引用在 README）：属“语言语义
  上限”参照——tpc 明确不做类型系统（接受项），此条只作“最深的语言知识长什么样”的观察，
  不进路线。
- 📌 **调研即仓库内文档**：`CALLC_PLAN.md`/`CFN_VARIADIC_PLAN.md`/`MSGSEND.md` 里带
  Zig/rustc 源码文件 + 行号对照（如 `ffi/llvm.zig::airCall` 4692-4966），与 tpc 的
  “见贤思齐 + 落档”同构（我们落 references.md，他落 `*_PLAN.md`）——差异是取舍，非优劣。

**可实现性（对 tpc）**

- 冻结式 `--emit-*` oracle：已有中间产物落盘的稳定化（P4.1 前置，小；接口契约先落档）。
- typed IR + 机械 lowering 分工：P4.1（多后端/LMM IR）设计参照，零新依赖。
- IR 不变量校验：可作 `tools/` 自查项（非门禁）或 debug 开关（先定义不变量清单）。
- MVS / comptime / std：**不实现**——超出“配置驱动前端”边界（README Known limitations
  已含“深语义在插件代码”）；作为语言包能力的观察样本保留。

**采集**：agent-reach（GitHub 仓库元数据）+ GitHub 源码检索（crate 结构/关键模块）+
jamlang.org reference（语言能力面）；未拉本地镜像。

**时机判断（2026-09-17 复核，作者定调）**：两边**不同线**，不是同一条曲线上的先后——
jam 在**语言语义深度**（MVS/comptime/ABI/typed IR 内部构造）上走得比 tpc 远，tpc 在
**工程化与工具面**（发布流程/门禁/格式保真/前置 lint/文档治理）上走得比 jam 远。
故借鉴按**条目类型**切，不按"成熟度先后"切：

- **现在可用**（结构/契约层，与语言成熟度无关）：typed IR + 机械 lowering 分工（P4.1 参照）、
  冻结式 `--emit-*` 转储做 oracle（我们已有中间产物落盘，缺"格式冻结"声明）、IR verifier
  形态、记录-重放模式。→ 需要时再从本档取。
- **留待复看**（依赖语言语义定型或 tpc 真做后端）：MVS 三规则在语义分析期的落地、
  comptime 求值器与 `cfn` 记录-重放细节、C ABI 分类。
  **触发条件**：tpc 启动 P4（多后端/LLVM 桥）时复看本节；或 jam 发布 v0.1（语义定型）后
  复看其内部构造。
- **只作观察**：flat/tag-dispatched AST + interning（性能导向；tpc 瓶颈在 parser 常数而非
  数据布局，且 AST 形态由引擎定——规则是数据）。

### 开发期工具链（Bifrost / SlopCop / Spec Kit，2026-09-18 调研 + 本机实测）

**定位**：三者服务的是"怎么做 tpc 这个工程"，不是 tpc 的设计来源（tpc 自身是分析器）。
放在本档是为了溯源：借了什么、为什么不整套引入。

**Bifrost（Brokk，Rust，Apache-2.0，本机 0.11.4）**

- 形态：多语言静态分析工具箱；接口四面——CLI / MCP server / LSP / Python client；
  能力面——统一 IR + RQL·JSON CodeQuery 结构查询 + 索引引用/调用/导入/层级 +
  有界 receiver/数据流/taint/typestate。
- 🔥 **证明层级与结果契约**：每个结果带 `proven`/`unproven`（不静默升级），诊断与截断
  进结果契约，文档明说"零结果只在声明的能力范围内成立"——与我们"缺验证不算完成"
  同调，值得作为分析器输出的参照。
- 🔥 **`slopcop` 工具集内置**：复杂度（cyclomatic/cognitive）、异常吞吃、长方法与上帝
  对象、结构重复、死代码与一次性抽象、测试断言薄弱、注释密度、git 热点、密钥样码——
  即托管 SlopCop 的服务端工具层，本地 CLI/MCP 直接可用。
- 语言面：C/C++/C#/Go/Java/JS/Kotlin/PHP/Python/Ruby/Rust/Scala/TS，**不含
  Verilog/SystemVerilog** → 只覆盖本仓 Python 侧；`grammar/**` 仍归仓内自查面。
- 实测（本机）：单次工具 2.4s（slopcop 报告族）/ 4.2s（`blast_radius`）；`scan` 小目录
  1.8s、13 文件 15.7s；`--policy --root . --sources <子集>` 35.7s。⚠ 缩 root（子目录当
  PATH）会让 Python 声明面策略 `inconclusive`——要完备结论必须保留仓库为 root。
- 信号面：探针 `tools/bifrost_probe/` 5/5 命中（1 warning + 4 note，无多余）；刚清理过的
  `preprocessor/` 0 命中。
- 可实现性：**已接入**为按需外部审查（规程 `policy/bifrost_audit.md`、AGENTS 自查工具
  一行、skill 入口）。不做的：不把它的策略当日常门禁（语言面窄 + 需外部二进制 +
  全量扫描分钟级）。

**SlopCop（Brokk，托管审计服务）**

- 形态：specialist agent（复杂度/规模/重复/错误处理/死代码/测试信号/注释意图）+ 静态
  分析 → 案件报告（评分 + 证据 + 可复制为 prompt 的建议），另有公开"Most Wanted"榜。
- 实测结论：其能力面就是 Bifrost 的 `slopcop` 工具集 → **不引入托管面**（收益与本地
  一致，代价是源码外传 + 结果不可本地复现 + 公开榜对"稳定展示态"的风险）。
- 💡 可借的是报告形态："每条结论带可回溯证据 + 下一步动作"，与仓内"收尾给结论分级"
  互补。

**Spec Kit（GitHub，★137k，MIT，agent skills 形态）**

- 形态：流程工具包三入口——SDD（`constitution → specify → plan → tasks → implement →
  converge`，循环到 Converged）、bug fixing（`bug-assess → bug-fix → bug-test`，扩展）、
  idea assessment（`intake → research → define → shape → decide`，扩展）。
- 实测产物：`specify init`（Copilot skills 模式）写 ~30 文件——`.github/skills/speckit-*`
  ×10 + `.specify/`（constitution / templates×5 / scripts(ps1)×6 / workflows / manifests）；
  已有仓库用 `specify init --here --force`，官方明说不重写应用、不为既有行为反向造规格。
- 🔥 **借走两条**（已落 `policy/collaboration.md`「实施节奏」，AGENTS.md 只留摘要）：bug 三分离的**先成因后动手**；
  **收尾结论分级** `verified`/`partial`/`failed` 且"缺验证不算完成"。
- 🔥 **constitution 纪律**（已落 `policy/collaboration.md`「指令文件自身纪律」）：只用已成立/已明确同意的原则，
  不为填模板发明标准。
- 💡 其余质量门（clarify/analyze/checklist）本仓门禁已覆盖；📌 spec 保鲜三模型
  （不可变历史/活契约/发现回流）与本仓"完成即删 + git log 存史"是不同选择，作对照。
- 可实现性：**只借范式，不引资产**——`.specify/` + 模板 + skills 会形成第二套记录体系
  （与"单一真相源、不留双路径"冲突），且 SDD 模板对单点缺陷修复/重构过重；若将来要
  对外交付"规格→任务→验证"链路，先评估只对**新语言包/新命令**这类有界新增启用。

