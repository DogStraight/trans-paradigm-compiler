# 参考与借鉴项目

> 分析过的项目及其对我们设计的影响。
> 最后更新：2026-08-14

| 项目 | 关系 | 主要启发 |
|------|------|---------|
| **[cmake-format](https://github.com/cheshirekow/cmakelang)** | 深度参考 | 多通道递进布局算法、Layout Tree 与 Syntax Tree 并行模式、注释重排、量化布局拒绝准则 |
| **[DmitrySoshnikov/syntax](https://github.com/DmitrySoshnikov/syntax)** | 概念验证 | "语言无关的语法规则作为独立资产"的可行性验证（11 年）、运算符优先级声明、多语言输出模式 |
| **[Prettier](https://github.com/prettier/prettier)** | 哲学参考 | "格式化即正确"理念、before/after 代码对比作为核心卖点 |
| **[Lark](https://github.com/lark-parser/lark)** | 架构对比 | Earley 与递归下降的取舍分析、grammar 格式对比 |
| **[Grammar-Kit](https://github.com/JetBrains/Grammar-Kit)** | 概念参考 | Pin 机制（最终未采用，但启发了 end_case + 回溯组合设计） |
| **[ANTLR](https://github.com/antlr/antlr4)** | 架构对比 | 工业级 parser generator 的定位与 TransParadigm 的差异 |
| **[Tree-sitter](https://github.com/tree-sitter/tree-sitter)** | 架构对比 | 增量解析与容错解析的思路参考 |
| **[INRIA Syntax](https://github.com/moosetechnology/syntax)** | 存在性确认 | C/Fortran 领域的配置驱动解析原型，验证了"不止我们在做" |
| **[textX](https://github.com/textX/textX)** | 架构对比 | Python 生态的 DSL 工作台，配置驱动理念的同行参考 |
| **[Spoofax](https://github.com/metaborg/spoofax)** | 架构对比 | 语言工作台（Java/Eclipse），编译期生成 vs 运行时 TOML。Statix scope graph 约束系统值得参考 |
| **Parser Combinators** ([pyparsing](https://github.com/pyparsing/pyparsing) / [nom](https://github.com/rust-bakery/nom)) | 架构对比 | 语法即代码 vs 配置驱动；Scannerless vs 管线分离；无渲染 vs Doc IR |
| **[parlex](https://github.com/ikhomyakov/parlex)** | 架构对比 | Rust 下仿 lex/yacc 编译期生成器；SLR(1) 运行时歧义消解对 end_case 有启发；但 v0.4 · 0⭐ · 4K 下载 · 个人项目无社区 · 参考价值有限 |
| **[ModelCC](https://modelcc.ikor.org/)** | 设计参考 | 模型驱动 parser generator（Java 类+注解 → 解析器）；Earley chart parser；内置引用解析 → ASG；`@Priority`/`@Associativity` 声明式消歧验证了 TransParadigm 声明式配置方向；但 r2015 后已停滞 |
| **[MoonBit](https://www.moonbitlang.com/)** | 架构对比 | Wasm-first 语言编译器（OCaml）。**双轨解析（Menhir LR + 手写递归下降并行）**。`parsing_core.ml` 的同步栈（syncs）错误恢复设计基于手写解析器对语法的深度理解。**TransParadigm 不适用**：sync 栈本质是语法知识（push_sync/pop_sync 硬编码在每条解析函数中），配置驱动引擎无法自动推导。全职团队（IDEA）、v0.10.3、极活跃。但语言设计（类型系统）+ 多后端与 TransParadigm 目标无关 |
| **[Taichi](https://github.com/taichi-dev/taichi)** | 架构对比 | 高性能数值计算嵌入式 DSL（嵌入 Python）。复用 Python `ast` 模块，无自定义 Lexer/Parser。**多级 IR 设计**（FrontendIR → LowerAST → SSA IR）的 lower_ast pass 与 TransParadigm normalizer 职责类似。但 LLVM/SPIR-V 代码生成、自动微分、GPU 后端均与 TransParadigm 目标无关。v1.7.4 · 28.3k⭐ · 极活跃 |
| **[Koine](https://github.com/chrsbats/koine)** | 架构对比 | Python 声明式 parser 工具包，YAML 定义完整 lex→parse→transpile 管线。底层基于 Parsimonious（PEG packrat）。**高度相似的设计哲学**：语法即数据（YAML/JSON/TOML）、管道式架构、配置驱动。但以下差异显著：(1) 依赖 yaml + parsimonious（非零依赖）；(2) PEG packrat 非递归下降+回溯；(3) Transpiler 模板驱动非 Doc IR；(4) 无语义分析/变换插件体系；(5) 无 EXT 注入机制。v0.10.3·2⭐·个人项目·最后更新 2025-09·维护停滞，**参考价值 💡**：subgrammar 跨文件多模块语法组织方式值得参考 |
| **[DHParser](https://gitlab.lrz.de/badw-it/DHParser)** | 架构对比 | Python EBNF parser generator，专注数字人文 DSL 快速原型（1.9.7·Apache 2.0）。完整 left-recursion 支持（squirrel parser LR 算法）、测试驱动语法开发 + post-mortem debugger、声明式 AST tree transformation。依赖 cython（可选）。无 Doc IR 渲染器、不关心多文件输出。**错误恢复方案不同**：TransParadigm 用反向解析器将错误节点暴露给用户，不依赖复杂的 post-mortem 工具 |
| **[Langium](https://github.com/eclipse-langium/langium)** | 架构对比 | TypeScript 语言工程框架（Eclipse·MIT·v4.3.0·1k⭐·极活跃）。底层 Chevrotain LL(k) 解析器，.langium 声明语法 → 生成 TypeScript AST 类型定义 + LSP 服务。**核心差异**：(1) 生成式解析器（LL(k)），非配置驱动；(2) LSP-first——框架直接产出语法高亮/补全/跳转等 IDE 功能；(3) TypeScript/Node.js 技术栈，非零依赖；(4) 渲染使用模板/visitor，非 Doc IR。**💡 可借鉴**：grammar DSL 直接生成 AST 类型定义的理念——TransParadigm 可考虑从 TOML production 推导 TypeScript 类型定义 |
| **[RADLR](https://github.com/acweathersby/radlr)** | 架构对比 | Rust parser compiler 框架（acweathersby·v1.0.1-beta2·0⭐·单人·最后更新 2025-09）。支持 LL/LR/RAD/GLL/GLR 等多种解析算法，生成字节码解析器。CLI + WASM 浏览器 Lab UI。**核心差异**：(1) Rust 实现，parser generator（非配置驱动运行时解析）；(2) 自举——解析器自身的语法由 RADLR 语法（.radlr 文件）定义并自解析；(3) 生成字节码而非运行时 AST 操作；(4) WASM 浏览器互动 Lab 是亮点。**💡 可借鉴**：parser 分类报告（LL/RD/RAD 等）及算法复杂度评估——TransParadigm 可借鉴其 metrics 概念用于调试输出 |
| **[Xtext](https://github.com/eclipse-xtext/xtext)** | 架构对比 | Eclipse 语言框架，生成式 vs 运行时 TOML。语法 DSL 生成 AST 类型定义的思路可借鉴，Maven 复杂度验证了零依赖方向正确 | Python monadic parser combinator（v2.2·MIT·零依赖·<800LOC·极成熟）。LL(infinity) 风格，组合子模式。**与 TransParadigm 不同道路**：语法即代码（Python 组合子）vs 配置驱动（TOML production）；从头组合出解析器而非写声明式规则。**💡 可借鉴**：极简实现（单文件<800行）、近10年零不兼容变更的稳定性 |
| **[Parsek](https://github.com/anptrs/parsek)** | 架构对比 | Python 轻量 parser combinator（v2.4.0·零依赖·单文件）。支持组合子+FSM 混合风格。**与 Parsy 同类，关键差异**：支持 FSM 格式定义，可用于简单状态机解析。v2.4.0·相较 Parsy 较新。**💡 可借鉴**：组合子+FSM 混合模式——TransParadigm 词法分析器使用 FSM，解析器使用递归下降，两套风格可互相参考 |
| **[wadler-lindig](https://github.com/patrick-kidger/wadler-lindig)** | 深度参考 | Python Wadler-Lindig pretty-printer（v0.1.7·MIT·零依赖·核心77行）。**与 TransParadigm Renderer 共享同一理论源头**（Wadler-Lindig Doc IR 算法）。**核心差异**：(1) 通用目的（repr/日志美化），非代码生成专用；(2) 无 layout DSL 配置，硬编码式使用；(3) 无 group/flat/broken 显式控制，自动选择。**TransParadigm 的 Renderer 在此算法之上扩展了 TOML 配置化的 layout DSL、primitives 体系、inline comment 回注等** |
| **[parsejoy](https://github.com/adewes/parsejoy)** | 架构对比 | YAML 定义 EBNF 语法→运行时解析（C++/Go/Python 三实现）。**自述"高度实验性且未完成"**。C++ 版依赖 Boost+LuaJIT+YAML-CPP（重）。Python 版有多个实验性实现（GLR parser）。**同**：YAML 语法即数据。**异**：(1) 多语言实现（非纯 Python）；(2) 依赖重（尤其 C++）；(3) GLR 算法非递归下降；(4) 无渲染器、无 AST 变换管线、无语义分析。**状态**：已停滞，仅实验用途 |
| **[MLIR ODS (llvm/llvm-project)](https://github.com/llvm/llvm-project)** | 深度参考 | 配置驱动 Operation 定义体系（TableGen .td），自动生成 C++ 构造器/验证器/序列化。39.3k⭐ · 极活跃 · LLVM 基金会 · 最后更新 2026-07-16。**详见下方调研报告** |
| **[CIRCT (llvm/circt)](https://github.com/llvm/circt)** | 设计参考 | MLIR-based 硬件编译器，FIRRTL→HW→SV→Verilog 多级下降管线。2.2k⭐ · 极活跃 · LLVM 基金会 · 最后更新 2026-07-16。**详见下方调研报告** |
| **[ClangIR / CIR (llvm/llvm-project)](https://clang.llvm.org/docs/ClangIR.html)** | 架构对比 | Clang 的 MLIR-based 中级 IR，C/C++ → CIR → LLVM IR。使用 ODS 定义所有操作。已上流到 llvm 主仓库。**详见下方调研报告** |
| **[JetBrains MPS](https://github.com/JetBrains/MPS)** | 架构对比 | 重量级语言工作台（项目化 DSL + 多目标生成）。1.7k⭐ · 极活跃（Apache-2.0）· 已配置 AGENTS.md/MCP 支持 coding agents。语言工作台天花板参照——重（Java/IDEA），非运行时配置驱动 |
| **[Ohm](https://github.com/ohmjs/ohm)** | 架构对比 | JS PEG + 语义操作完全分离 + 语法 OO 扩展 + 在线可视化编辑器。5.5k⭐ · 53 贡献者 · 130 依赖方 · v17 半年前。最接近"语法实验台"——但只到 parse+semantics，无渲染/变换/多语言管线 |
| **[desugar](https://github.com/michaelmillar/desugar)** | 方向参考 | Rust browser-native 编译器工作室：逐步实现 pass + 每 pass 可视化 + 导出独立工程。0⭐ · 单人 · 4 月前活跃。最接近"编译器模拟器"概念——但定位教学（expression-based，无类型检查/后端） |
| **[ldtk](https://github.com/Terran-One/ldtk)** | 架构对比 | TS 模块化语言开发工具包。1⭐ · 3 年前停滞 · WIP 未成。同生态位小众项目的冷启动现状参照 |

## 生态位追踪（2026-08-14 调研）— "语言即数据"的四个活跃分支

> 调研方式：GitHub topic（language-workbench / parser-generator）+ 逐项目源码。
> 结论先行：**"配置驱动完整管线"依然没人做，但"语言即数据"分化出四个分支**——
> 按"活跃度 × 定位距离"逐个追踪如下。

### cairn（Scala，2 周前更新）— 与 P3 增量解析直接相关

- 仓库：`eurisko-info-lab/cairn`（Apache-2.0，research software v0.1）
- **框架**：语言 = `Fragment` 片段组合（`provides/requires/excludes`）→ `Compose.compose` 推流合并 → 内容寻址（每个语言/产物有 digest）。**双向文法**：一个 `GrammarSpec` 同时生成 parse + print，`RoundTrip.check` 验证 parse∘print 定律，`Concrete.put` 做**格式保留编辑**（字节级 splice，只替换目标 span）。另有 ΔL（语义变更语言）、签名账本、Rosetta 多目标投影（Lean/Coq/Scala/Rust）
- **目标差异**：tpc = 语言工具链（格式化/lint/编译产物）；cairn = **语言的版本控制**（语义变更、哈希、账本、可复现发布）。"git 换成了语言"
- **形态差异**：无 linter（token 级反解析）、无 formatter（品类对齐）、无第二语言实证——力气花在"语义可信"（哈希/证明/账本），tpc 花在"工具链完整"
- **💡 对 tpc 的直接价值**：`Grammar.scala` 的增量失效（`invalidateFrom` token 缓存）**正是 TODO P3 增量解析要做的**，cairn 已实现并配了测试（`MetaPreserveFormatSuite`）——tpc P3 可直接参考它的"双向文法 + 格式保留替换"做法

### lvca（OCaml，2022 停）— provenance 一等公民

- 仓库：`joelburget/lvca`（OCaml，dune 构建）
- **框架**：抽象语法用 `valence`（绑定数量/种类）描述，`[%lvca.abstract_syntax_module]` ppx 从字符串生成 OCaml 类型。核心关注**绑定与变量**（nominal/De Bruijn 双向转换）、双向类型检查（`bidirectional` 包）
- **目标差异**：lvca 是**研究语言理论**的工具（"Language Verification, Construction, and Analysis"，名字自比 LUCA）；tpc 是工程语言工具链
- **形态差异**：抽象语法是**代码生成**（ppx 编译期），tpc 是**运行时 TOML**。无渲染器（Fmt 库）、无 linter、无预处理器——停在"语言定义 + 语义"
- **💡 对 tpc 的价值**：`Provenance.t`（每个节点带 range）是**一等公民**，正是 tpc 的 `Node` 缺的（TODO P3 前置）。lvca 的 provenance 设计可直接借鉴

### rascal（Java，活跃）— 元编程语言的完整实现

- 仓库：`usethesource/rascal`（CWI/SWAT 研究机构出品，源流可溯至 1984 年 ASF+SDF Meta-Environment，40 年学术传承）
- **框架**：**元编程语言**——Rascal 是一门完整语言（type checker + interpreter + compiler + REPL），`grammar(...)` 定义文法，GLR 广义解析器运行时生成 parser。标准库 + 大量语言分析库（Java/C++/PHP/Python/JS analysis），有 LSP/VS Code 集成。杀手锏是**具体语法模式匹配**（元语言里写对象语言模式）+ **IDE/LSP 生成**（一个语言定义 → VSCode 扩展）
- **目标差异**：rascal = "用元语言做语言工作"（面向语言研究者/大规模源码分析）；tpc = "给 DSL 作者配置语言管线"。消费方不同
- **形态差异**：**元语言 + 生成式**（写 Rascal 代码定义文法）vs tpc **配置式 + 通用引擎**（写 TOML 数据）。rascal 在 parser 侧做歧义管理 + 容错解析；tpc 在 parser 前用 linter 挡——同一语法的两种消费方式，各有取舍
- **借鉴点**：具体语法模式匹配是 rascal 独有优势，tpc 的 transform 插件若借鉴（用 TOML 声明的模式匹配 AST），模型代写门槛可更低——大 feature，v0.2 再议

### NegI（Lua，2 周前更新）

- 仓库：`MegadronA03/NegI` — "Semantic substrate"，偏解释器/沙箱/能力安全
- 与 tpc 目标基本无关，但证明"语义底座"方向有人活跃

### Koine 作者动向（2025-09 停更后）

- 作者 Chris Bates（`chrsbats`）2025-09 后转向：`outlines-chat`（local chat model + outlines 结构化生成）、`SLIP`（"world modeling" 语言，18 小时前仍活跃）
- **信号**：Koine 作者从"人定义语言的工具"转向"模型世界里的语言/模型输出约束"——**"配置驱动 + 模型可代写"这个组合依然无人占据**



> 调研方式：GitHub topic（language-workbench / parser-generator）+ 具体项目主页。
> 聚焦 tpc 定位：配置驱动、多语言、完整管线的轻量语言工具，以及"编译器模拟器/语法实验台"方向。

### 分层地图
- **重量级语言工作台**：MPS（1.7k⭐·活跃）、Langium（TS·1k⭐·活跃）、Xtext/Spoofax——IDE 集成、Java/TS、生成式
- **活跃配置/声明式 DSL 工具**：textX（Python·852⭐·640 依赖方·活跃）、Ohm（JS·5.5k⭐）——单点（DSL 元模型 / parse+semantics）
- **停滞/小众配置管线**：Koine（2⭐·2025 停）、ldtk（1⭐·停）、parsejoy/INRIA Syntax（停）
- **编译器工作室/教学**：desugar（0⭐·单人）——逐步 pass 可视化，最接近"编译器模拟器"
- **生成式 parser generator**（513 仓库）：ANTLR/PEG.js/lalrpop/TatSu/BNFC 等——生成解析器，不同赛道

### 结论
1. **直接竞品（配置驱动 + 完整管线 + 多语言 + 渲染 + 零依赖）无活跃对手**——生态两极分化：要么重（MPS/Langium），要么单点（parser generator），中间地带空着
2. 但**生态冷**：language-workbench 全 topic 14 仓库、多数 1-5⭐ 且停滞；同定位新项目（Koine/desugar/ldtk）冷启动普遍失败
3. **必须正视 textX**：Python + 活跃 + 852⭐，是"Python 里配置驱动搭语言"的第一入口。差异定位：textX = 单一语法→元模型+解释（DSL 快速建模）；tpc = 多语言配置驱动完整管线 + 渲染器 + 插件体系（语言级管线引擎）

### 自由度 vs 上手度（定位反思）
- tpc 把"语言知识外部化"→ 用户要自己提供语言知识（配置+插件）→ **自由度极高，但挑人**：只适合有范式要固化的人 / 编译器·语言爱好者 / 有现成语法想管线化的人；不适合"想开箱即用"的人
- 对比：textX 用元模型+自动生成降自由度换上手度（852⭐）；Koine 用完整配置换自由度（2⭐·停）——不是自由度越高越好，是**自由度/上手度的平衡点**
- 结论："挑人"是定位的必然，不是缺陷。关键是**被挑中的人体验要好**（引导/文档/模板，见 TODO P2.0 + c4 模板化），而不是把受众扩大到所有人
