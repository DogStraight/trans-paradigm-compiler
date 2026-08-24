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

### 格式化与渲染

| 项目 | 关系 | 一句话价值总结 |
|------|------|----------------|
| [cmake-format](https://github.com/cheshirekow/cmakelang) | 设计参考 | 多通道递进布局算法、Layout Tree 与 Syntax Tree 并行模式、注释重排、量化布局拒绝准则 |
| [Prettier](https://github.com/prettier/prettier) | 概念参考 | "格式化即正确"理念、before/after 代码对比 |
| [wadler-lindig](https://github.com/patrick-kidger/wadler-lindig) | 概念参考 | Wadler-Lindig Doc IR 算法（Renderer 的理论源头） |

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
