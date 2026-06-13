# PyV 编译器 → Verilog

配置驱动的 Verilog 编译框架，支持语法解析 → 语义分析 → 代码生成 → 格式化的完整流水线。
设计为可扩展框架：切换目标语言只需更换 `rules_verilog/` 配置。

## 流水线

```
Verilog 源码
    │
    ▼
┌─────────────┐
│    Lexer    │  词法分析 → Token 流（含行列位置）
│  main_lexer │  基于 token.toml 配置
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Parser    │  语法分析 → AST
│  pratt_parser│  Pratt 表达式解析 + 规则系统
│  rule_selector│  语法规则由 rules_verilog/*.toml 定义
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Optimizer  │  AST 变换 → 简化 AST
│ ast_optimizer│  展平 first/rest/Block/BeginEnd
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Semantic   │  符号表构建 → 带 symbol_ref 的 AST
│  Analyzer   │  作用域管理 + 标识符解析
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Code     │  配置驱动 → Verilog 代码
│  Generator  │  模板引擎 {{ }} / {{#}} / {{?}}
│  (Visitor)  │  CG 模板与语法规则合并在同一文件
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Formatter  │  缩进对齐 → 格式化 Verilog
│ verilog_    │  处理 begin/end/endcase 层级
│ formatter   │
└──────┬──────┘
       │
       ▼
  gen/*.v  (生成代码)
```

## 项目结构

```
pyv_compiler/
├── README.md
├── define.py                    # Token, Node, GrammarRule, FileManager
├── err.py                       # 异常定义
├── code_generator.py            # 代码生成器（模板引擎 + 访问者模式）
│
├── grammar/                     # 外部配置（核心）
│   ├── token.toml               # Token 定义
│   ├── symbol_level.toml        # 运算符优先级与结合性
│   └── rules_verilog/           # Verilog 语法 + 生成 + 语义规则（合一）
│       ├── 00_blocks.toml       # Root / Block / BeginEnd
│       ├── 01_module.toml       # ModuleDecl / ParameterList / ParamDecl
│       ├── 02_declarations.toml # PortDecl / WireDecl / RegDecl / LocalParamDecl
│       ├── 03_always.toml       # AlwaysBlock / SensitivityList / EdgeSense
│       ├── 04_statements.toml   # If/Case/Assign/Blocking/NonBlocking
│       └── 05_expressions.toml  # 字面量 / 运算符 / Pratt 节点
│
├── lexer/                       # 词法分析器
│   ├── __init__.py
│   ├── main_lexer.py
│   ├── lexer_utils.py
│   └── number_fsm.py            # 数字字面量 FSM 解析
│
├── parser/                      # 语法分析器
│   ├── __init__.py
│   ├── main_parser.py
│   ├── pratt_parser.py          # Pratt 表达式解析
│   ├── parser_context.py        # 解析上下文 + 回溯快照
│   ├── rule_selector.py         # 规则选择器（token → 候选规则）
│   └── feature_analyze.py       # 产生式预计算加速
│
├── optimizer/
│   └── ast_optimizer.py         # AST 变换管道（展平/提取）
│
├── analyzer/                    # 语义分析
│   ├── __init__.py
│   ├── scope.py                 # Scope / Symbol / get_symbol_kinds
│   └── semantic_analyzer.py     # 符号表构建 + 标识符解析
│
├── formatter/
│   ├── __init__.py
│   └── verilog_formatter.py     # Verilog 格式化（缩进/块合并）
│
├── scripts/
│   └── gen_mermaid_fsm.py       # FSM 图生成
│
├── docs/
│   └── fsm_diagram.md
│
└── verilog/                     # Verilog 编译测试
    ├── run_pipeline.py          # 端到端流水线入口
    ├── run_optimizer.py
    ├── ref/                     # 参考源文件
    │   ├── ref_alu.v
    │   ├── ref_counter.v
    │   ├── ref_fsm.v
    │   └── ...
    ├── gen/                     # 生成代码输出
    ├── ast/                     # 优化后 AST JSON
    └── symbols/                 # 符号表 JSON
```

## 配置驱动的三条信息

每条语法规则在 TOML 中包含三个维度的配置：

```toml
[RegDecl]
# ── 语法
production = ["keyword.reg", "@Range?", "id", "symbol.base.semicolon"]
end_case = ["newline"]
# ── 生成
template = "    reg{{?range}} [{{range}}]{{/range}} {{ reg_name }};"
# ── 语义
symbol_kind = "reg"
symbol_name = "reg_name"
```

## 运行测试

```bash
cd verilog

# 端到端测试
python run_pipeline.py ref_fsm
python run_pipeline.py ref_alu
python run_pipeline.py ref_counter

# 输出对比（DIFF 行数 = 0 表示完全一致）
```
lexer = Lexer()
tokens = lexer.tokenize("""
x: int = 10
y: int = 20
sum: int = x + y
""")

# 2. 语法分析
parser = Parser()
ast = parser.parse(tokens)

# 3. 代码生成
cg = CodeGenerator()
outputs = cg.generate(ast)      # → {"output.v": "生成的内容..."}
outputs = cg.optimize(outputs)  # 文本级优化
cg.dump(outputs)                # 写入 output/ 目录

print(outputs["output.v"])
```

## 配置详解

### 1. Token 定义 (`grammar/token.toml`)

定义所有 token 类型及其匹配模式，包括符号、关键字、字面量、括号等。支持正则表达式定义复杂模式。

```toml
[symbol.base]
add = "+"
sub = "-"
multiple = "*"

[id.keyword]
if = "if"
for = "for"
module = "module"

[literal]
number = "\\d+"
string = "(\".*\")|('.*')"
```

### 2. 语法规则 (`grammar/rules.toml`)

采用类 EBNF 格式定义产生式规则。支持以下语法元素：

**模块化加载**：语法规则现在从 `grammar/rules/` 目录加载。目录下所有 `.toml` 文件按文件名排序后合并，同名规则后者覆盖前者。以下划线 `_` 开头的文件被跳过。你可以禁用某个模块（加 `_` 前缀）、新增模块（加新文件）、或覆盖规则（加同名的后加载文件）。

`grammar/rules/` 目录内容示例：

```
grammar/rules/
├── 00_literals.toml       # 字面量及原子表达式
├── 01_operators.toml      # 运算符单元
├── 02_expressions.toml    # 表达式（Pratt 解析）
├── 03_calls.toml          # 函数调用
├── 04_types.toml          # 类型系统
├── 05_literals_expr.toml  # 字面量表达式
├── 06_statements.toml     # 语句
├── 07_control_flow.toml   # 控制流
├── 08_imports.toml        # 导入语句
├── 09_blocks.toml         # 块结构
└── 10_conditions.toml     # 条件表达式
```

如果目录不存在或为空，自动回退到单文件 `rules.toml`。

| 语法 | 含义 |
|------|------|
| `"token.type"` | 匹配特定 token 类型 |
| `@RuleName` | 调用另一个规则 |
| `"A\|B\|C"` | 分支选择 |
| `item*` | 零次或多次 |
| `item+` | 一次或多次 |
| `item?` | 可选 |
| `( ... )` | 分组 |

```toml
[VarInit]
production = ["id", "symbol.base.colon", "@Type", "symbol.base.equal", "@Initializer"]
end_case = ["newline"]
[VarInit.node]
var_name = "$1"
type = "$3"
value = "$5"
```

### 3. 运算符优先级 (`grammar/symbol_level.toml`)

运算符优先级由数组顺序决定（从上到下优先级递增），支持指定结合性和前缀/后缀位置。

```toml
[[operator]]
symbol = "or"
arity = 2
assoc = "left"

[[operator]]
symbol = "+"
arity = 2
assoc = "left"

[[operator]]
symbol = "-"
arity = 1
position = "prefix"
```

### 4. 代码生成规则 (`grammar/cg_rules.toml`)

定义 AST 节点到目标代码的映射模板。也支持**模块化加载**，从 `grammar/cg_rules/` 目录加载所有 `.toml` 文件。模板语法：

| 语法 | 含义 |
|------|------|
| `{{var_name}}` | 渲染子节点（递归 visit） |
| `{{var_name.value}}` | 沿路径取叶子值 |
| `{{#child}}...{{.}}...{{/child}}` | 遍历列表 |
| `{{?alias}}...{{/alias}}` | 条件包含 |
| `{{!alias}}...{{/alias}}` | 条件取反 |

条件分支模板（如 `UnaryOp` 根据 `position` 选择不同模板）：

```toml
[UnaryOp]
match = "position"
[[UnaryOp.case]]
when = "prefix"
template = "{{ op }}{{ operand }}"

[[UnaryOp.case]]
when = "postfix"
template = "{{ operand }}{{ op }}"
```

多文件输出规则：

```toml
[[file_rules]]
node_type = "Root"
file_name = "output.v"
header = "// Generated by PyV Compiler\n\n"
```

## 架构说明

### 词法分析器 (Lexer)

基于规则匹配的词法分析器，从 `token.toml` 中读取所有 token 定义，对输入源码进行逐字符扫描。支持缩进跟踪（`space.indent` / `space.dedent`）和注释跳过。

### 语法分析器 (Parser)

采用 Pratt 解析 + 规则匹配的混合策略：

- **表达式**：由 Pratt 解析器 (`pratt_parser.py`) 处理，运算符优先级和结合性从 `symbol_level.toml` 动态加载。
- **语句**：由规则匹配引擎 (`main_parser.py`) 处理，通过特性分析 (`feature_analyze.py`) 预计算每个产生式的特征，实现快速规则选择。
- **内置回滚机制**：使用 Python `with` 语句 + 自定义异常实现匹配失败时的自动回滚。

### 代码生成器 (CodeGenerator)

基于访问者模式的配置驱动代码生成器：

- **访问者模式**：`visit(node)` 根据 `node.name` 自动分派到对应模板。
- **模板引擎**：`TemplateEngine` 将模板字符串解析为语法树，支持嵌套、迭代、条件渲染。
- **多文件输出**：`[[file_rules]]` 控制文件分发策略，支持从一个 AST 生成多个输出文件。
- **优化管道**：`optimize()` 提供文本级后处理（去多余空行等）。

## 当前状态

### 已完成

- ✅ Token 定义框架（符号、关键字、字面量、括号）
- ✅ 词法分析器（基础 token 识别、缩进跟踪）
- ✅ 语法规则定义框架（类 EBNF、产生式、属性映射）
- ✅ Pratt 表达式解析器（完整的运算符优先级链）
- ✅ 语句规则匹配（变量声明、赋值、if/while/for、import）
- ✅ AST 构建（`Node` 类 + `dump()` 调试输出）
- ✅ 代码生成器框架（访问者模式 + 模板引擎 + 多文件输出）

### 待完成

参见 `TODO.md`，主要包括：
- 扩展数字字面量格式（科学计数法、进制前缀、位宽等）
- 更多语法结构支持（函数定义、类定义等）
- 代码生成规则的完善和调试

## 依赖

- Python 3.11+（使用内置 `tomllib` 解析 TOML 配置）
