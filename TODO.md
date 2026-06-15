# TODO

## 近期目标 — Verilog 编译器完成

### 🟢 已完成

- [x] **Lexer — 词法分析**
  - FSM 驱动的数字解析（十进制/浮点/十六进制/二进制/Verilog 位宽字面量）
  - Token 行列位置信息（`start.line/column` → `end.line/column`）
  - indent/dedent 缩进处理
  - Verilog 关键字支持（module/always/begin/end/posedge/negedge/assign/localparam…）
  - `$` 符号支持（系统函数调用 `$clog2`）

- [x] **Parser — 语法分析**
  - Pratt 表达式解析器（优先级/结合性由 `symbol_level.toml` 配置）
  - 规则系统：TOML 定义 production + end_case + inline
  - Block 缩进块、BeginEnd 命名块
  - 模块声明：参数列表、端口列表
  - 声明：wire / reg / localparam（单值 + 多值逗号分隔）
  - 语句：always 块、if/case 分支、阻塞/非阻塞赋值、assign
  - 表达式：算术/比较/逻辑/位运算、连接符/复制符、索引访问
  - 节点位置信息：从 Token → AST Node 完整传递

- [x] **Optimizer — AST 优化**
  - 关键字值提取、id 值提取
  - first/rest 列表展平、repeat/sequence 展平
  - Block 展平、Root 展平
  - ElseChain 归一化

- [x] **SemanticAnalyzer — 语义分析**
  - Scope 作用域链（enter/exit/resolve/declare）
  - Symbol 符号表（kind/decl_node/width）
  - Identifier → Declaration 链接（`symbol_ref`）
  - 符号类别从 TOML 配置动态发现（`get_symbol_kinds()`）
  - 符号表输出为 `symbols/*.json`

- [x] **CodeGenerator — 代码生成**
  - 配置驱动：语法规则 + 生成模板合并为同一 TOML 文件
  - 模板引擎：`{{path}}`、`{{#list}}`、`{{?cond}}`、`{{!not}}`、`@first/@last/@index`
  - 容器节点兜底（`iter_children()` 统一子节点迭代）
  - 文件头规则（`[[file_rules]]`）
  - 文本级优化（去多余空行）

- [x] **Formatter — 代码格式化**
  - Verilog 格式器（缩进/块合并/端口对齐）
  - begin/end/endcase 层级追踪
  - end + else/else if + begin 合并
  - if/else 单句体缩进

- [x] **Node 类重构**
  - `start`/`end` 位置属性
  - `add_sub_node()` 匿名子节点
  - `iter_children()` 统一子节点迭代器（sub_node + 命名属性）
  - 移除 `add_attr("name")` hack（`Identifier` 规则统一使用 `content`）

- [x] **测试覆盖**
  - ALU（组合逻辑、连续赋值）
  - 计数器（参数、状态寄存器）
  - 状态机 FSM（三段式、case 内 begin/end）
  - D 触发器

### 🟡 进行中 / 待增强

- [ ] **Lexer 缩进改造** — 改为关键字触发（`begin`/`case`/`module`），跳过续行对齐
- [ ] **域管理 + 符号表集成到配置** — `scope_open` / `scope_kind` / `symbol_kind` 字段已加入，Parser 集成待完成
- [ ] **配置文件的目录化整合** — `_token.toml` / `_symbol_level.toml` 已搬入 `rules_verilog/`，Lexer/Parser 已支持从 `rules_dir` 自发现，后续新增语言只需一套目录

### 🔴 未开始 — 需 Scope/Symbol 就绪后

- [ ] **`integer` / `genvar` 声明** — 简单语法规则 + CG 模板
- [ ] **多维数组** — `reg [7:0] mem [0:255];`
- [ ] **`for` 循环语句** — `for (i = 0; i < N; i = i + 1)`
- [ ] **`generate for / if / case`** — generate 域管理 + 循环/条件生成
- [ ] **`function` / `task`** — 子语言解析器 + 独立作用域
  - 需先在 `token.toml` 注册 `keyword.function` / `keyword.task` / `keyword.endfunction` / `keyword.endtask`
  - 需在 TOML 规则中标记 `scope_open = true` / `scope_kind = "function"`
  - 函数/任务的内部 `input`/`output` 要注册到自己的域而非模块域
- [ ] **`$clog2` 等系统函数** — Pratt 表达式支持

### 📋 延伸规划

#### 预处理器（配置驱动）
- [ ] **`define / `include / `ifdef 支持**
  - 作为独立流水线阶段插在 Lexer 之前
  - 预处理规则由 TOML 配置（`_preprocessor.toml`），保持项目风格
  - 优先级中等，可作为一个微型独立项目之后实现

#### DSL 生成器完备化
- [ ] **多语言验证** — 目前只有 Verilog 一个实例，完备性不足
- [ ] **新增第二语言试验** — 用同一套 TOML rules → Doc IR 流水线验证通用性
- [ ] **自动化 diff 测试** — 当前 gen/*.v 与 ref/*.v 靠肉眼对比

#### 对标 Pyverilog 的元能力提取
- [ ] **研究 Pyverilog 数据流分析**（`dataflow_analyzer.py`）
  - 模块连线提取、信号绑定、常量传播
  - 评估是否能作为独立的 analyzer pass 嵌入流水线
- [ ] **研究 Pyverilog 控制流分析**（`controlflow_analyzer.py`）
  - FSM 状态机提取、状态转换图
  - 评估是否能作为元能力抽取
- [ ] **研究其 AST 节点设计** — 每个节点一个 Python 类 vs 通用 `Node` 的取舍

#### 其他
- [ ] **常量折叠** — 编译期计算常量表达式（`W-1` → `7`）
- [ ] **类型/位宽推断** — 从表达式树推导信号位宽
- [ ] **跨文件导入** — `import` 语句 + 符号注册
- [ ] **VS Code 插件** — 语法高亮 + 补全 + 跳转定义
- [ ] **配置驱动的 LSP** — CLI 命令 `--complete` / `--hover` / `--goto-def`