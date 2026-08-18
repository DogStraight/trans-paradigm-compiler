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
| [Koine](https://github.com/chrsbats/koine) | 语法即数据（YAML/JSON/TOML）、管道式架构、配置驱动；subgrammar 跨文件多模块语法组织 |
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
