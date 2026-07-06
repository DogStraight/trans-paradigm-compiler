# 参考与借鉴项目

> 分析过的项目及其对我们设计的影响。
> 最后更新：2026-07-02

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
| **[dynparser](https://github.com/jleahred/dynparser)** | 设计参考 | 运行时规则加载（PEG 文本 / 宏内联 / API 追加）、自举、AST 后处理链 |
| **Parser Combinators** ([pyparsing](https://github.com/pyparsing/pyparsing) / [nom](https://github.com/rust-bakery/nom)) | 架构对比 | 语法即代码 vs 配置驱动；Scannerless vs 管线分离；无渲染 vs Doc IR |
| **[parlex](https://github.com/ikhomyakov/parlex)** | 架构对比 | Rust 下仿 lex/yacc 编译期生成器；SLR(1) 运行时歧义消解对 end_case 有启发；但 v0.4 · 0⭐ · 4K 下载 · 个人项目无社区 · 参考价值有限 |
| **[ModelCC](https://modelcc.ikor.org/)** | 设计参考 | 模型驱动 parser generator（Java 类+注解 → 解析器）；Earley chart parser；内置引用解析 → ASG；`@Priority`/`@Associativity` 声明式消歧验证了 PyV 声明式配置方向；但 r2015 后已停滞 |
| **[MoonBit](https://www.moonbitlang.com/)** | 架构对比 | Wasm-first 语言编译器（OCaml）。**双轨解析（Menhir LR + 手写递归下降并行）** 对比验证可借鉴。`parsing_core.ml` 的同步栈错误恢复设计值得参考。全职团队（IDEA）、v0.10.3、极活跃。但语言设计（类型系统）+ 多后端与 PyV 目标无关 |
| **[Taichi](https://github.com/taichi-dev/taichi)** | 架构对比 | 高性能数值计算嵌入式 DSL（嵌入 Python）。复用 Python `ast` 模块，无自定义 Lexer/Parser。**多级 IR 设计**（FrontendIR → LowerAST → SSA IR）的 lower_ast pass 与 PyV normalizer 职责类似。但 LLVM/SPIR-V 代码生成、自动微分、GPU 后端均与 PyV 目标无关。v1.7.4 · 28.3k⭐ · 极活跃 |
