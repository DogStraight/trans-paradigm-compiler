# 参考与借鉴项目

> 分析过的项目及其对我们设计的影响。
> 最后更新：2026-07-17

| 项目 | 关系 | 主要启发 |
|------|------|---------|
| **[cmake-format](https://github.com/cheshirekow/cmakelang)** | 深度参考 | 多通道递进布局算法、Layout Tree 与 Syntax Tree 并行模式、注释重排、量化布局拒绝准则 |
| **[DmitrySoshnikov/syntax](https://github.com/DmitrySoshnikov/syntax)** | 概念验证 | "语言无关的语法规则作为独立资产"的可行性验证（11 年）、运算符优先级声明、多语言输出模式 |
| **[Prettier](https://github.com/prettier/prettier)** | 哲学参考 | "格式化即正确"理念、before/after 代码对比作为核心卖点 |
| **[Lark](https://github.com/lark-parser/lark)** | 架构对比 | Earley 与递归下降的取舍分析、grammar 格式对比 |
| **[Grammar-Kit](https://github.com/JetBrains/Grammar-Kit)** | 概念参考 | Pin 机制（最终未采用，但启发了 end_case + 回溯组合设计） |
| **[ANTLR](https://github.com/antlr/antlr4)** | 架构对比 | 工业级 parser generator 的定位与 PyV 的差异 |
| **[Tree-sitter](https://github.com/tree-sitter/tree-sitter)** | 架构对比 | 增量解析与容错解析的思路参考 |
| **[INRIA Syntax](https://github.com/moosetechnology/syntax)** | 存在性确认 | C/Fortran 领域的配置驱动解析原型，验证了"不止我们在做" |
| **[textX](https://github.com/textX/textX)** | 架构对比 | Python 生态的 DSL 工作台，配置驱动理念的同行参考 |
| **[Spoofax](https://github.com/metaborg/spoofax)** | 架构对比 | 语言工作台（Java/Eclipse），编译期生成 vs 运行时 TOML。Statix scope graph 约束系统值得参考 |
| **Parser Combinators** ([pyparsing](https://github.com/pyparsing/pyparsing) / [nom](https://github.com/rust-bakery/nom)) | 架构对比 | 语法即代码 vs 配置驱动；Scannerless vs 管线分离；无渲染 vs Doc IR |
| **[parlex](https://github.com/ikhomyakov/parlex)** | 架构对比 | Rust 下仿 lex/yacc 编译期生成器；SLR(1) 运行时歧义消解对 end_case 有启发；但 v0.4 · 0⭐ · 4K 下载 · 个人项目无社区 · 参考价值有限 |
| **[ModelCC](https://modelcc.ikor.org/)** | 设计参考 | 模型驱动 parser generator（Java 类+注解 → 解析器）；Earley chart parser；内置引用解析 → ASG；`@Priority`/`@Associativity` 声明式消歧验证了 PyV 声明式配置方向；但 r2015 后已停滞 |
| **[MoonBit](https://www.moonbitlang.com/)** | 架构对比 | Wasm-first 语言编译器（OCaml）。**双轨解析（Menhir LR + 手写递归下降并行）**。`parsing_core.ml` 的同步栈（syncs）错误恢复设计基于手写解析器对语法的深度理解。**PyV 不适用**：sync 栈本质是语法知识（push_sync/pop_sync 硬编码在每条解析函数中），配置驱动引擎无法自动推导。全职团队（IDEA）、v0.10.3、极活跃。但语言设计（类型系统）+ 多后端与 PyV 目标无关 |
| **[Taichi](https://github.com/taichi-dev/taichi)** | 架构对比 | 高性能数值计算嵌入式 DSL（嵌入 Python）。复用 Python `ast` 模块，无自定义 Lexer/Parser。**多级 IR 设计**（FrontendIR → LowerAST → SSA IR）的 lower_ast pass 与 PyV normalizer 职责类似。但 LLVM/SPIR-V 代码生成、自动微分、GPU 后端均与 PyV 目标无关。v1.7.4 · 28.3k⭐ · 极活跃 |
| **[Koine](https://github.com/chrsbats/koine)** | 架构对比 | Python 声明式 parser 工具包，YAML 定义完整 lex→parse→transpile 管线。底层基于 Parsimonious（PEG packrat）。**高度相似的设计哲学**：语法即数据（YAML/JSON/TOML）、管道式架构、配置驱动。但以下差异显著：(1) 依赖 yaml + parsimonious（非零依赖）；(2) PEG packrat 非递归下降+回溯；(3) Transpiler 模板驱动非 Doc IR；(4) 无语义分析/变换插件体系；(5) 无 EXT 注入机制。v0.10.3·2⭐·个人项目·最后更新 2025-09·维护停滞，**参考价值 💡**：subgrammar 跨文件多模块语法组织方式值得参考 |
| **[DHParser](https://gitlab.lrz.de/badw-it/DHParser)** | 架构对比 | Python EBNF parser generator，专注数字人文 DSL 快速原型（1.9.7·Apache 2.0）。完整 left-recursion 支持（squirrel parser LR 算法）、测试驱动语法开发 + post-mortem debugger、声明式 AST tree transformation。依赖 cython（可选）。无 Doc IR 渲染器、不关心多文件输出。**错误恢复方案不同**：PyV 用反向解析器将错误节点暴露给用户，不依赖复杂的 post-mortem 工具 |
| **[Langium](https://github.com/eclipse-langium/langium)** | 架构对比 | TypeScript 语言工程框架（Eclipse·MIT·v4.3.0·1k⭐·极活跃）。底层 Chevrotain LL(k) 解析器，.langium 声明语法 → 生成 TypeScript AST 类型定义 + LSP 服务。**核心差异**：(1) 生成式解析器（LL(k)），非配置驱动；(2) LSP-first——框架直接产出语法高亮/补全/跳转等 IDE 功能；(3) TypeScript/Node.js 技术栈，非零依赖；(4) 渲染使用模板/visitor，非 Doc IR。**💡 可借鉴**：grammar DSL 直接生成 AST 类型定义的理念——PyV 可考虑从 TOML production 推导 TypeScript 类型定义 |
| **[RADLR](https://github.com/acweathersby/radlr)** | 架构对比 | Rust parser compiler 框架（acweathersby·v1.0.1-beta2·0⭐·单人·最后更新 2025-09）。支持 LL/LR/RAD/GLL/GLR 等多种解析算法，生成字节码解析器。CLI + WASM 浏览器 Lab UI。**核心差异**：(1) Rust 实现，parser generator（非配置驱动运行时解析）；(2) 自举——解析器自身的语法由 RADLR 语法（.radlr 文件）定义并自解析；(3) 生成字节码而非运行时 AST 操作；(4) WASM 浏览器互动 Lab 是亮点。**💡 可借鉴**：parser 分类报告（LL/RD/RAD 等）及算法复杂度评估——PyV 可借鉴其 metrics 概念用于调试输出 |
| **[Xtext](https://github.com/eclipse-xtext/xtext)** | 架构对比 | Eclipse 语言框架，生成式 vs 运行时 TOML。语法 DSL 生成 AST 类型定义的思路可借鉴，Maven 复杂度验证了零依赖方向正确 | Python monadic parser combinator（v2.2·MIT·零依赖·<800LOC·极成熟）。LL(infinity) 风格，组合子模式。**与 PyV 不同道路**：语法即代码（Python 组合子）vs 配置驱动（TOML production）；从头组合出解析器而非写声明式规则。**💡 可借鉴**：极简实现（单文件<800行）、近10年零不兼容变更的稳定性 |
| **[Parsek](https://github.com/anptrs/parsek)** | 架构对比 | Python 轻量 parser combinator（v2.4.0·零依赖·单文件）。支持组合子+FSM 混合风格。**与 Parsy 同类，关键差异**：支持 FSM 格式定义，可用于简单状态机解析。v2.4.0·相较 Parsy 较新。**💡 可借鉴**：组合子+FSM 混合模式——PyV 词法分析器使用 FSM，解析器使用递归下降，两套风格可互相参考 |
| **[wadler-lindig](https://github.com/patrick-kidger/wadler-lindig)** | 深度参考 | Python Wadler-Lindig pretty-printer（v0.1.7·MIT·零依赖·核心77行）。**与 PyV Renderer 共享同一理论源头**（Wadler-Lindig Doc IR 算法）。**核心差异**：(1) 通用目的（repr/日志美化），非代码生成专用；(2) 无 layout DSL 配置，硬编码式使用；(3) 无 group/flat/broken 显式控制，自动选择。**PyV 的 Renderer 在此算法之上扩展了 TOML 配置化的 layout DSL、primitives 体系、inline comment 回注等** |
| **[parsejoy](https://github.com/adewes/parsejoy)** | 架构对比 | YAML 定义 EBNF 语法→运行时解析（C++/Go/Python 三实现）。**自述"高度实验性且未完成"**。C++ 版依赖 Boost+LuaJIT+YAML-CPP（重）。Python 版有多个实验性实现（GLR parser）。**同**：YAML 语法即数据。**异**：(1) 多语言实现（非纯 Python）；(2) 依赖重（尤其 C++）；(3) GLR 算法非递归下降；(4) 无渲染器、无 AST 变换管线、无语义分析。**状态**：已停滞，仅实验用途 |
| **[MLIR ODS (llvm/llvm-project)](https://github.com/llvm/llvm-project)** | 深度参考 | 配置驱动 Operation 定义体系（TableGen .td），自动生成 C++ 构造器/验证器/序列化。39.3k⭐ · 极活跃 · LLVM 基金会 · 最后更新 2026-07-16。**详见下方调研报告** |
| **[CIRCT (llvm/circt)](https://github.com/llvm/circt)** | 设计参考 | MLIR-based 硬件编译器，FIRRTL→HW→SV→Verilog 多级下降管线。2.2k⭐ · 极活跃 · LLVM 基金会 · 最后更新 2026-07-16。**详见下方调研报告** |
| **[ClangIR / CIR (llvm/llvm-project)](https://clang.llvm.org/docs/ClangIR.html)** | 架构对比 | Clang 的 MLIR-based 中级 IR，C/C++ → CIR → LLVM IR。使用 ODS 定义所有操作。已上流到 llvm 主仓库。**详见下方调研报告** |
