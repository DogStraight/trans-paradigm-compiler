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
