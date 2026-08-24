# 参考与借鉴项目

> 本文件记录影响 tpc 设计的参考项目及其借鉴点（设计来源可追溯）。
> 与 `tests/e2e/samples/real/CREDITS.md`（第三方样本署名）互补：
> 前者管"设计来源"，后者管"代码来源"。

## 项目 → 借鉴点

| 项目 | 借鉴点 |
|------|--------|
| [cmake-format](https://github.com/cheshirekow/cmakelang) | 多通道递进布局算法、Layout Tree 与 Syntax Tree 并行模式、注释重排、量化布局拒绝准则 |
| [DmitrySoshnikov/syntax](https://github.com/DmitrySoshnikov/syntax) | "语言无关的语法规则作为独立资产"的可行性验证、运算符优先级声明、多语言输出模式 |
| [Prettier](https://github.com/prettier/prettier) | "格式化即正确"理念、before/after 代码对比 |
| [Lark](https://github.com/lark-parser/lark) | Earley 与递归下降的取舍分析、grammar 格式对比 |
| [Grammar-Kit](https://github.com/JetBrains/Grammar-Kit) | Pin 机制（未采用，启发了 end_case + 回溯组合设计） |
| [ANTLR](https://github.com/antlr/antlr4) | 工业级 parser generator 的定位差异 |
| [Tree-sitter](https://github.com/tree-sitter/tree-sitter) | 增量解析与容错解析的思路 |
| [INRIA Syntax](https://github.com/moosetechnology/syntax) | C/Fortran 领域的配置驱动解析原型 |
| [textX](https://github.com/textX/textX) | Python 生态的 DSL 工作台，配置驱动理念 |
| [Spoofax](https://github.com/metaborg/spoofax) | 语言工作台（Java/Eclipse），编译期生成 vs 运行时 TOML；Statix scope graph 约束系统 |
| Parser Combinators ([pyparsing](https://github.com/pyparsing/pyparsing) / [nom](https://github.com/rust-bakery/nom)) | 语法即代码 vs 配置驱动；Scannerless vs 管线分离；无渲染 vs Doc IR |
| [parlex](https://github.com/ikhomyakov/parlex) | SLR(1) 运行时歧义消解对 end_case 的启发 |
| [ModelCC](https://modelcc.ikor.org/) | 模型驱动 parser generator；`@Priority`/`@Associativity` 声明式消歧验证了声明式配置方向 |
| [MoonBit](https://www.moonbitlang.com/) | 双轨解析（Menhir LR + 手写递归下降并行）；sync 栈错误恢复（不适用：sync 栈是语法知识，配置驱动引擎无法自动推导） |
| [Taichi](https://github.com/taichi-dev/taichi) | 多级 IR 设计（FrontendIR → LowerAST → SSA IR）的 lower_ast pass 与 normalizer 职责类似 |
| [lyra](https://github.com/hankhsu1996/lyra) | 架构对比 | SystemVerilog 仿真工具链（C++/Bazel，复用 slang AST），同期活跃的同龄人；多级 IR + 927 case 测试组织可借鉴（详见下方深调研） |
| [VAST](https://github.com/trailofbits/vast) | 深度参考 | 程序分析向的 MLIR 塔式 IR 管线；Tower 机制（每个 pass 后克隆模块 + 记录转换步骤 + 位置反向链接）是 provenance 链的工程化范本（详见下方深调研） |
| [Foundry](https://github.com/foundry-rs/foundry) | 架构对比 | Ethereum 开发工具链（Rust，10k+★）；模块化切片（forge/cast/anvil/chisel 独立组件）与碎片化 changelog 是工程组织的范本（详见下方深调研） |
| [vbcc](https://github.com/Leffmann/vbcc) | 深度参考 | 1989 年起的可移植 C 编译器，13 个目标后端；machines/ 目录一个后端一个目录的极简组织（详见下方深调研） |
| [Koine](https://github.com/chrsbats/koine) | 架构对比 | 语法即数据（YAML/JSON/TOML）+ 管道式 + subgrammar 多文件组织；聚焦快速 DSL 原型（详见下方深调研） |
| [DHParser](https://gitlab.lrz.de/badw-it/DHParser) | 完整 left-recursion 支持、测试驱动语法开发、声明式 AST 变换；错误恢复方案不同（反向解析器 vs post-mortem） |
| [Langium](https://github.com/eclipse-langium/langium) | grammar DSL 直接生成 AST 类型定义的理念（从 TOML production 推导类型定义） |
| [RADLR](https://github.com/acweathersby/radlr) | parser 分类报告（LL/RD/RAD 等）及算法复杂度评估（metrics 概念用于调试输出） |
| [Xtext](https://github.com/eclipse-xtext/xtext) | 语法 DSL 生成 AST 类型定义；Maven 复杂度验证了零依赖方向 |
| [Parsek](https://github.com/anptrs/parsek) | 组合子+FSM 混合模式（词法 FSM + 解析递归下降） |
| [wadler-lindig](https://github.com/patrick-kidger/wadler-lindig) | Wadler-Lindig Doc IR 算法（Renderer 的理论源头） |
| [parsejoy](https://github.com/adewes/parsejoy) | YAML 语法即数据（实验性，未完成） |
| [MLIR ODS (llvm/llvm-project)](https://github.com/llvm/llvm-project) | 配置驱动 Operation 定义体系（TableGen .td），自动生成 C++ 构造器/验证器/序列化 |
| [CIRCT (llvm/circt)](https://github.com/llvm/circt) | MLIR-based 硬件编译器，FIRRTL→HW→SV→Verilog 多级下降管线 |
| [ClangIR / CIR (llvm/llvm-project)](https://clang.llvm.org/docs/ClangIR.html) | Clang 的 MLIR-based 中级 IR，使用 ODS 定义所有操作 |
| [JetBrains MPS](https://github.com/JetBrains/MPS) | 重量级语言工作台（项目化 DSL + 多目标生成）——天花板参照 |
| [Ohm](https://github.com/ohmjs/ohm) | JS PEG + 语义操作分离 + 语法 OO 扩展 + 在线可视化编辑器 |
| [desugar](https://github.com/michaelmillar/desugar) | 逐步 pass 可视化（编译器模拟器方向） |
| [ldtk](https://github.com/Terran-One/ldtk) | TS 模块化语言开发工具包 |

## 深度参考（增量解析 / provenance / 元编程）

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

- 定位：Trail of Bits 出品（DARPA 资助研究），C/C++ 程序分析与插桩的 MLIR 基础设施——"a tower of IRs as MLIR dialects"，为分析场景提供不同抽象层级的 IR 选择
- **项目印象**：444★/34 forks，Apache-2.0；lib/vast 分 9 个子系统（ABI/CodeGen/Conversion/Dialect/Frontend/Interfaces/server/Target/Tower/Util）；8 个 IR 方言（ABI/Builtin/Core/HighLevel/LowLevel/Meta/Parser/Unsupported）；github.io 文档站 + Compiler Explorer 在线体验；CI（build/linter）全绿
- **Tower 机制（核心亮点）**：每个 pass 运行后**克隆模块**存入 module_storage，同时记录"转换步骤链"（pass 路径 + 位置变换），每个 operation 的位置编码反向链接（backlink）——从高层 IR 任意节点可回溯它是怎么从源文本一步步变来的。这是 provenance 链的工程化范本
- **与 tpc 的差异**（各有取舍，非优劣）：

| 维度 | VAST | tpc |
|------|------|-----|
| 目标 | 程序分析/插桩（分析友好 IR 塔） | 配置驱动工具链（格式化/lint/展开） |
| IR 组织 | MLIR 方言塔（同源多级） | Doc IR（Wadler-Lindig）+ AST |
| 转换 | pass 管线 + 模块克隆（重但可回溯） | transform 配置驱动 + 插件原语 |
| 依赖 | LLVM/MLIR（重） | Python 3.11+ 零外部依赖 |
| 位置追踪 | 一等公民（loc 编码 backlink） | 解析诊断有 span；Node 缺 token span（TODO P3 前置） |

- **值得参考的部分**：
  - 🔥 转换步骤链 + 位置反向链接：每个 pass 后记录"从哪来"——对应 tpc TODO P3 的 token span 前置 + 变换路径注释恢复（锚点漂移的根本解决思路），VAST 证明了"转换可追溯"可以做成架构级机制
  - 💡 同源多级 IR（塔）而非各自为政：分析者按需选层级——与 tpc 的"切片"理念呼应（按阶段取用，而非必须全管线）
  - 💡 方言分层命名（HighLevel/LowLevel/Core/Meta）对 IR 设计有启发

### Foundry（Rust）— Ethereum 开发工具链（2026-08 深调研）

- 定位：blazing fast、portable、modular 的 Ethereum 应用开发工具链，Rust 编写；forge（构建/测试/fuzz/调试/部署）、cast（链交互瑞士军刀）、anvil（本地节点）、chisel（Solidity REPL）
- **项目印象**：10570★/2607 forks（今日还在推），Apache-2.0；crates/ 多 crate 组织（anvil 拆 core/rpc/server 子 crate）；`.changelog/` 目录每个 PR 一个 changelog 碎片文件（release 时聚合）——工程组织教科书级；官方文档站 + benchmark 页 + 开发者指南
- **与 tpc 的差异**（各有取舍，非优劣）：

| 维度 | Foundry | tpc |
|------|---------|-----|
| 领域 | EVM 智能合约开发（编译+测试+链交互+节点） | 配置驱动语言工具链（格式化/lint/展开） |
| 语言 | Rust + 重型依赖生态 | Python 3.11+ 零外部依赖 |
| 组织 | 多 crate 工作区（组件即 crate） | 单包 + 多语言包（grammar/<lang>） |
| 分发 | foundryup 工具链管理器 + 预编译二进制 | tpc-fmt/tpc-lint/tpc exe（Nuitka 单文件） |
| 更新 | 持续集成发布（每 PR 一条 changelog 碎片） | 版本化发布 + CHANGELOG 手写 |

- **值得参考的部分**：
  - 🔥 模块化切片实证：forge/cast/anvil/chisel 是四个独立可用的组件，共享核心库——与 tpc 的切片哲学同构，且证明了"工具链按能力切分"在 10k★ 项目里成立
  - 🔥 碎片化 changelog：每个 PR 一个 `.changelog/*.md`，发布时聚合——解决"手写 changelog 漏记/拖延"的工程化答案（tpc 可评估：文档型仓库是否值得引入，或维持当前手动小节）
  - 💡 foundryup 工具链管理器（版本切换 + 安装脚本）——tpc 若做多版本分发可参考
  - 💡 benchmark 公开页（getfoundry.sh/benchmarks）——把性能数据当作品资产

### vbcc（C）— 1989 年起的可移植 C 编译器（2026-08 深调研）

- 定位：Volker Barthelmann 与 Frank Wille 的可移植 C 编译器（1989 年起，至今维护）；一个编译器支撑 13 个目标后端（6502/832/alpha/bi386/c16x/hc12/i386/m68k/m68ks/ppc/qnice/vidcore/z）
- **项目印象**：GitHub 镜像（Leffmann/vbcc）25★/12 forks，5 commits（2016-2023 快照）；原作持续维护（官网 + Amiga 社区生态）。109 个 C/H 文件约 2.7MB；优化器是经典单文件大 pass（regs.c 65KB、opt.c 65KB、loop.c 62KB、alias.c 21KB）；doc/ 用 texinfo 写全套手册（vbcc_main + 每后端一册）；自带 vcpr/vprof/vsc/ucpp（预处理器/剖析/源码检查）组件
- **与 tpc 的差异**（各有取舍，非优劣）：

| 维度 | vbcc | tpc |
|------|------|-----|
| 定位 | 单语言（C）多目标后端编译器 | 多语言包通用管线（后端即语言包） |
| 后端抽象 | machines/ 目录一个后端一个目录（含 make.rules） | grammar/<lang>/ 一个语言一个目录（TOML + 插件） |
| 优化 | 手写 pass（alias/cse/regs/loop/range） | 配置驱动变换（无传统优化器） |
| 组件 | 自带预处理器/剖析器/源码检查器 | 管线内建 preprocessor/linter/analyzer |
| 生命周期 | 30+ 年单作者长跑（+Frank Wille 维护） | 2024 起个人项目 |

- **值得参考的部分**：
  - 🔥 machines/ 目录抽象：一个后端一个目录、通用接口 + 每后端文档——与 tpc 的 grammar/<lang> 语言包组织同构，验证了"多目标=多目录"的极简抽象足够支撑 13 个后端
  - 💡 单文件大 pass 的克制：不搞过度分层，pass 就是文件——与 tpc"零外部依赖、单包"的克制一致
  - 💡 30 年单作者长跑：可移植性（13 后端）本身就是项目生命力的来源——tpc 的"多语言包"若扩展，可复刻这种"换后端不换引擎"的生存策略
  - 📌 优化器是手写 pass（非配置驱动）——与 tpc 定位不同，tpc 的"配置驱动变换"覆盖浅层语义，深层优化不在此设计目标内
