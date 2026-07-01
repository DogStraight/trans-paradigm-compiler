# 参考与借鉴项目

> 分析过的项目及其对我们设计的影响。
> 最后更新：2026-07-01

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
