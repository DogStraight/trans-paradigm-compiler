# PyV Compiler — 路线图与设计决策

> 项目公开前的内部记录。包含已实现的架构决策、待完成的缺口、以及悬而未决的设计问题。
> 保持谦虚：可能无人问津，也可能被质疑"有什么意义"。无论如何，这些思考值得写下来。

---

## 一、项目定位

**PyV Compiler** 是一个用 Python 编写的、配置驱动的 Verilog 编译器基础设施。

不是要替代 Vivado/Verilator，而是提供一个**可嵌入、可扩展、可定制**的 Verilog 解析与生成工具链。

### 核心价值

1. **TOML 配置驱动** — 语法规则、AST 变换、代码生成布局全部由 TOML 配置，不改 Python 代码就能扩展语言
2. **五阶段管线可插拔** — Lexer / Parser / Normalizer / SemanticAnalyzer / Renderer，每阶段可独立替换
3. **Wadler-Lindig Doc IR** — 基于代数数据类型的漂亮打印引擎，自动处理缩进和换行
4. **增强语法层** — 通过 production injection 和 transform 引擎，在 Verilog 上叠加自定义类型系统
5. **零外部依赖** — 纯 Python 3.11+，只用标准库

### 非目标

- 不是综合工具（不输出网表）
- 不是仿真器
- 不是 Verilator 替代品
- 不支持完整 SystemVerilog（只支持可综合 Verilog 子集 + 有限 SV 扩展）

---

## 二、架构总览

### 管线（顺序不可颠倒）

```
源文件 → Lexer → Parser → Normalizer → SemanticAnalyzer → Renderer → 生成代码
                                        ↓
                                   AstTransformer（可选变换插件）
```

### 各阶段职责

| 阶段 | 输入 | 输出 | 配置来源 |
|------|------|------|----------|
| **Lexer** | 源文本 | Token 流 | `_token.toml` |
| **Parser** | Token 流 | AST（原始） | `rules_verilog/*.toml` |
| **Normalizer** | AST（原始） | AST（规范） | `normalize_config.toml`（仅辅助配置） |
| **SemanticAnalyzer** | AST（规范） | AST + SymbolTable | 规则自声明（`scope`/`symbol`/`identifier_ref`） |
| **AstTransformer** | AST + SymbolTable | AST（变换后） | `[RuleName.transform]` + handler 注册 |
| **Renderer** | AST（规范/变换后） | 格式化文本 | 规则 layout DSL + `_style.toml` |

### 关键设计决策

```
D1. 配置化走到底
    所有语言行为由 TOML 定义，Python 代码只做调度和执行。
    好处：新增语言不需要改编译器代码。
    代价：配置错误在运行时暴露，缺乏编译时检查。

D2. 递归下降 + 回溯
    不使用 parser generator（YACC/Bison），而是手写递归下降。
    好处：错误信息可控，AST 节点可自定义，注入机制灵活。
    代价：性能不如 LALR(1)，极端嵌套可能栈溢出。

D3. 增强语法层与核心规则隔离
    rules_verilog_ext/ 与 rules_verilog/ 分离，
    通过 inject_productions 在加载期挂载。
    好处：核心语法不被污染，EXT 可独立发布。
    代价：注入冲突需要手动解决。

D4. Normalizer 只消除 parser 内部结构
    只消除 optional/repeat/seq 包装节点。
    语法层结构（DeclaratorList、Statement 等）一律保留。
    确保 Renderer 看到的是稳定 AST 形状。

D5. Transform 引擎：原语优先，handler 兜底
    expand（lookup+foreach+emit）覆盖大多数场景。
    复杂逻辑通过 @transform_handler 注册 Python handler。
    不试图用配置描述一切。
```

---

## 三、实现状态

### ✅ 已实现（2026-06-29）

**核心管线**
- [x] Lexer — 关键字/符号/字面量/注释/空白 Token 化
- [x] Parser — 递归下降 + Pratt 表达式 + 回溯 + 块管理
- [x] Normalizer — 消除 optional/repeat/seq + 值提取 + 属性合并
- [x] SemanticAnalyzer — 作用域管理 + 符号注册 + 标识符解析
- [x] Renderer — Wadler-Lindig Doc IR + 布局 DSL
- [x] AstTransformer — 插件管线

**Verilog 语法（134 条规则）**
- [x] 模块声明（ANSI/旧风格端口）
- [x] wire/reg/integer 声明
- [x] parameter/localparam
- [x] always 块 + 事件控制
- [x] assign 语句（连续赋值）
- [x] if/case 语句
- [x] for 循环
- [x] function/task（ANSI + 旧风格端口）
- [x] 模块实例化（命名/位置参数）
- [x] 阻塞/非阻塞赋值
- [x] 表达式（运算符优先级 + 拼接 + 复制）
- [x] 语句分层（CtrlStmt / ProcAssignStmt / CallStmt / DeclStmt / InstStmt）
- [x] 事件等待 @(posedge clk);

**增强语法基础设施**
- [x] EXT 层加载（rules_verilog_ext/）
- [x] Production injection（两层注入 + 传播）
- [x] Inject replace（替换 production / end_case）
- [x] 目标寻址语法（`RuleName.production[N]` / `RuleName.end_case`）
- [x] Transform 引擎（expand / replace / delete + custom handler）
- [x] lookup 原语支持 type 表和 scope 符号表

**质量保证**
- [x] 33 个端到端测试用例
- [x] 全量回归脚本（`run_all_tests.py`）
- [x] AST debug dump
- [x] Token dump
- [x] Inline comment 指纹回注

### ⏳ 待完成

**P0 — 核心 Verilog 完备**
- [ ] `generate` / `generate if` / `generate case` / `genvar`
- [ ] `forever` / `repeat` / `wait` / `disable`
- [ ] `always_ff` / `always_comb` / `always_latch`
- [ ] `initial`
- [ ] `force` / `release` / `deassign`
- [ ] 数组声明 `reg [7:0] mem [0:255]`
- [ ] `while` 循环

**P1 — EXT 类型系统**
- [ ] `keyword.revert` 注册
- [ ] `keyword.fn` 或复用 `task`/`function`
- [ ] `TypeDecl` 解析规则（type name(params) { roles + methods }）
- [ ] `RevertDecl` 规则（`revert other_role;`）
- [ ] `TypeMethod` 规则（`fn read: { }`）
- [ ] `TypeVar` 规则（`spi spi_conn;`）
- [ ] `TypedPortDecl` TypeParamList 支持（`spi(0,8).slave`）
- [ ] 方法调用链（`spi_io.read().spi_data`）
- [ ] Transform: RevertDecl → direction reversal
- [ ] Transform: TypeMethod → stub expansion
- [ ] Transfrom: TypeVar → default role expansion
- [ ] Renderer layouts for all new rules
- [ ] `ref_spi_inf.v` 完整解析 → 生成

**P2 — 上下文敏感文法**
- [ ] 前向引用解析（decl before use 需要双遍或符号表辅助的回溯）
- [ ] 声明与使用的二义性消解（identifier 是类型名还是实例名）
- [ ] 预处理器集成（`` `define / `include / `ifdef `` 在 Lexer 前展开）

**P3 — 质量**
- [ ] 输出整洁度审查（无多余空格/空行）
- [ ] i18n 错误/日志信息
- [ ] 全量 diff 自动化（不依赖肉眼对比）

**P3 — 工程化**
- [ ] 新手教程：从零添加一条语法规则（10 分钟可跟做）
- [ ] `--validate-config` 模式：启动时检查 TOML 配置完整性
- [ ] `pyproject.toml` / `setup.py`
- [ ] PyPI 发布
- [ ] CI（GitHub Actions）
- [ ] 贡献指南（CONTRIBUTING.md）

---

## 四、悬而未决的设计问题

### Q1. TypeDecl 的 body 结构
...
```
type spi (params) {
    master : input miso, output clk, mosi, cs;
    slave  : revert master;
    fn read : { ... }
}
```
...
- role 定义是 `role_name : port_decl_list`
- `revert` 是引用另一个 role 并反转方向
- `fn` / `task` / `function` 定义接口方法
...
**待定**：fn body 里是否能包含 always/assign，还是只做接口签名？

### Q2. 类型参数传递
...
### Q3. revert 精确语义
...
### Q4. 无 role 的类型变量
...
### Q5. 方法调用链
...
### Q6. 展开后的命名空间
...
---

## 五、今晚新增待办项（2026-06-30 会话）

### P0 — 格式化器 + 容错解析
- [ ] pipieline mode: 新增 `format` 模式（Lexer→Parser→Normalizer→Renderer，跳过 Analyzer+Transform）
- [ ] 错误容忍：Parser 在语法错误时返回部分 AST，不直接抛异常终止
- [ ] `--format` CLI 入口：输入 .v 文件 → 输出格式化后的 .v 文件
- [ ] 保留原始注释位置（不丢失行内注释）
- [ ] 参考 Prettier 的"格式化即正确"理念

### P0 — 配置化预处理器
- [ ] `base/_preprocess.toml` — include_pattern、search_paths、defines 配置
- [ ] `lexer/preprocess.py` — 正则驱动的 include 展开（纯文本替换，不涉及解析）
- [ ] 引擎级管线模式：include_pattern = "" 时跳过预处理步骤
- [ ] 可动态开关（format 模式下关闭预处理保留源文本完整性）

### P1 — 核心 Verilog 完备（已有）
- [ ] generate / generate if / generate case / genvar
- [ ] forever / repeat / wait / disable
- [ ] always_ff / always_comb / always_latch
- [ ] initial / force / release / deassign
- [ ] 数组声明 reg [7:0] mem [0:255]
- [ ] while 循环
- [ ] 条件运算符 ?: 完整支持（已部分实现）
- [ ] 增强注释解析（块注释 /**/ 跨行）

### P1 — 上下文敏感文法增强
- [ ] pre_scan ← 已完成（2026-06-30）
- [ ] scope_stack ← 已完成（2026-06-30）
- [ ] peek 跨域引用 ← 已完成（2026-06-30）
- [ ] identifier_ref 属性级类型解析 ← 已完成（2026-06-30）
- [ ] RuleSelector 运行时 scope 查询消歧
- [ ] import / `include 跨文件符号传播

### P2 — 增强语法层
- [ ] TypeDecl ParamList 支持（`spi(0,8).slave`）
- [ ] TypeMethod / TypeVar 规则
- [ ] 方法调用链解析（`spi_io.read().data`）
- [ ] RevertDecl transform → port direction reversal
- [ ] 更多类型用例（不同参数、嵌套类型、多 role）

### P3 — 工程化
- [ ] pipeline modes 配置化（`_pipeline.toml` 声明各模式阶段子集）
- [ ] 新手教程：从零添加一条语法规则（10 分钟可跟做）
- [ ] `--validate-config` 模式：启动时检查 TOML 配置完整性
- [ ] 输出整洁度审查（无多余空格/空行）
- [ ] 全量 diff 自动化（不依赖肉眼对比）
- [ ] pyproject.toml / setup.py
- [ ] CI（GitHub Actions）
- [ ] 贡献指南（CONTRIBUTING.md）
- [ ] 许可证选择（MIT）

### 架构级讨论（远期）
- [ ] LLVM IR 对接可行性（需要 LLVM 专家协助）
- [ ] "任意语言转任意语言"的 Transform 管线分叉
- [ ] WASM 后端输出
- [ ] 增量解析（类似 tree-sitter 的热重载）
- [ ] 可视化语法编辑器（前端 Web 应用）
output spi_io_mosi;
output spi_io_miso;
output spi_io_cs;
```

前缀是 `实例名_信号名`。但如果两个实例同名冲突？在作用域层面防止？

---

## 五、已知局限

1. **预处理器** — `\`define` / `\`include` / `\`ifdef` 不支持
2. **SystemVerilog** — 只覆盖可综合子集，不支持 assertion / coverage / randomization
3. **性能** — Python 递归下降解析器，不适合 >100K 行的大文件
4. **类型检查** — Transform 引擎不做类型检查（只做结构变换）
5. **无 LSP** — 没有 language server，不能在编辑器里实时告警
6. **自举** — 编译器不是用 PyV 自己写的（也没必要）

---

## 六、对开源的期望

项目还年轻，2024 年起步，2026 年才跑通全管线。跟 Yosys（2013）和 Verilator（1994）比，它还是个孩子。

但它有一个这些项目没有的东西——**它是为 AI 时代设计的**。语法规则是 TOML 数据，不是 C++ 代码。LLM 可以读它、写它、调试它。改语言不需要改引擎——改 TOML 就行。这个差异会随着时间的推移越来越明显。

短期（1 年）：
- 让几个 Verilog 用户真的用上它
- 在开源芯片社区攒点口碑

中期（3 年）：
- 成为 Verilog 工具链里的一个可用选项
- 让至少一种新语言通过 PyV 实现前端

长期（10 年）：
- 等 AI 能直接生成和调试 TOML 规则的那一天，这个项目的架构价值会自然显现

十年不长。

---

*最后更新：2026-06-30*
