# PyV Compiler — 项目约定

## 架构

5 阶段管线顺序不可颠倒：

```
源文件 → Lexer → Parser → Normalizer → SemanticAnalyzer → Renderer → 生成代码
```

- **Lexer**: 读取 `_token.toml` 词法定义
- **Parser**: 匹配 `rules_verilog/*.toml` 语法规则，生成原始 AST
- **Normalizer**: 消除 `optional`/`repeat`/`seq` 包装节点
- **SemanticAnalyzer**: 作用域管理 + 符号注册（可选阶段）
- **Renderer**: 根据 layout DSL 生成格式化文本

## 语法规则（TOML）

### 文件结构

```
grammar/rules_verilog/
├── _token.toml          词法定义（Lexer 加载）
├── _pratt.toml          运算符优先级（Pratt 加载）
├── 00_blocks.toml       块结构（Root, ModuleBlock, BeginEnd）
├── 01_module.toml       模块声明
├── 02_declarations.toml 端口、wire/reg 声明
├── 03_always.toml       always 块
├── 04_statements.toml   语句（if/case/赋值/function/task）
└── 05_expressions.toml  表达式与运算符
```

以下划线 `_` 开头的文件被跳过，不会参与规则注册。

### 规则定义

```toml
[RuleName]
[RuleName.parser]
production = ["token1", "@RuleRef", "token2"]
end_case = ["keyword.end", "newline"]
inline = true

[RuleName.parser.node]
attr_name = "$1"           # 引用第 N 个 production 元素
attr_list = ["$1", "$2"]   # 合并多个引用

[RuleName.renderer]
layout = { line = [...] }
body = { indent = true, source = "..." }
tail = { text = "end", break = 2 }
```

### 关键规则

- **production**: 产生式列表，支持 `@RuleName`（规则引用）、`token_type`（字面 Token）、`(...)`（分组）、`...?`（可选）、`...*`（零次或多次）、`...|...`（分支）
- **end_case**: 规则匹配后的终止符检查列表（为空列表时不检查）
- **inline**: 为 true 时规则被扁平化，只保留第一个属性映射的子节点
- **block_start / block_end**: 块规则，用于 `parse_block` 管理
- **atomic**: 原子规则，在解析器中有优先级排序
- **pratt**: 使用 Pratt 解析器处理表达式

### $N 路径语法

- `$1` — 引用第 1 个 production 元素的匹配结果
- `$2.sub_node[0]` — 索引访问
- `$3.items[*].sub_node[1]` — `[*]` 对整个列表做 map 操作
- N 不能超过 production 数组长度

## Renderer Layout DSL

### 原语

| 原语 | 作用 | flat 模式 | broken 模式 |
|------|------|-----------|-------------|
| `Text` | 字面文本 | 不变 | 不变 |
| `Line` (SoftLine) | 软换行 | 空格 | 换行 |
| `Break` | 硬换行 | 换行 | 换行 |
| `group(doc)` | 二象性选择 | flat 版本 | broken 版本 |
| `Nest(n, doc)` | 增加缩进 | 加缩进 | 加缩进 |

### 布局配置

- **layout**: 节点的主布局（head 的别名）
- **head**: 节点头部（`line` / `join` / `group` / `ref` 等）
- **body**: 节点主体（`indent` 控制缩进，`source` 指定数据源）
- **tail**: 节点尾部（`break` 控制前后空行数）

### 常见陷阱

- `join` 原语默认包裹 `group()`，`SoftLine` 会被展平为空格
- `SoftLine` 在 `group` 内 flat 模式变为空格，`Break` 不受影响
- `Nest` 会叠加——父级 body indent + 子级 join nest 可能产生多余空格
- `{ break = true }` 在 `line` 顶层会触发 `has_soft` 导致整行被 group 包裹

## SemanticAnalyzer

- 作用域由 TOML 中 `[RuleName.analyzer] scope = { name_attr, kind }` 声明
- 符号由 `symbol = { kind, name_attr }` 声明
- 标识符引用由 `identifier_ref = true` 声明
- 只做作用域管理 + 显示符号注册，不做隐式声明/常量折叠

## 测试

所有测试用例在 `verilog/ref/ref_*.v`，生成结果在 `verilog/gen/gen_*.v`。
全量回归：`python verilog/run_all_tests.py`。
单用例：`python verilog/run_pipeline.py <test_name>`。
