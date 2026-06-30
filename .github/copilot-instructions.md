# PyV Compiler — 项目约定

## 项目概述

配置驱动的 Verilog 编译框架（纯 Python 3.11+，零外部依赖）。
**本质硬编码保留在代码中，偶然硬编码全部配置化**。详见 [README](../../README.md)。

## 代码风格

见 `/memories/repo/style.md`——硬编码阈值、架构约束、命名约定、架构决策完整记录。

## 管线（顺序不可颠倒）

```
源文件 → Lexer → Parser → Normalizer → SemanticAnalyzer → Renderer → 生成代码
                                           ↓
                                      AstTransformer（可选）
```

- **Lexer**: 读取 `_token.toml` 词法定义
- **Parser**: 匹配 `rules_verilog/*.toml` 语法规则，生成原始 AST
- **Normalizer**: 消除 `optional`/`repeat`/`seq` 包装节点（详见 [ast_normalization.md](../../docs/ast_normalization.md)）
- **SemanticAnalyzer**: 作用域管理 + 符号注册（可选阶段）
- **Renderer**: 根据 layout DSL 生成格式化文本（详见 [renderer_design.md](../../docs/renderer_design.md)）
- **AstTransformer**: 后阶段变换插件管线（用于类型展开等高级功能）

## CLI 用法

```bash
python main.py pipeline [test_name]           # CLI 入口
python verilog/run_pipeline.py [test_name]     # 直接运行（默认 led_blinker）
python verilog/run_all_tests.py                # 全量回归（--verbose / --json）
```

## 语法规则（TOML）

### 文件结构

```
grammar/rules_verilog/
├── _token.toml          词法定义（Lexer 加载）
├── _symbol_level.toml   运算符优先级（Pratt 加载）
├── 00_blocks.toml       块结构（Root, ModuleBlock, BeginEnd）
├── 01_module.toml       模块声明
├── 02_declarations/     端口、wire/reg/localparam 声明
├── 03_always.toml       always 块
├── 04_statements/       语句（if/case/赋值/function/task/模块实例化）
└── 05_expressions.toml  表达式与运算符
```

以下划线 `_` 开头的文件/目录被跳过，不会参与规则注册。子目录（不以下划线开头且不含 `.`）会被递归加载。

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

### 关键规则属性

- **production**: 产生式列表，支持 `@RuleName`（规则引用）、`token_type`（字面 Token）、`(...)`（分组）、`...?`（可选）、`...*`（零次或多次）、`...|...`（分支）
- **end_case**: 规则匹配后的终止符检查列表。**空列表 = 不是语句级规则**，不会被纳入候选列表（曾因 `end_case` 默认值 `[]` 导致过滤条件失效的 bug）
- **inline**: 为 true 时规则被扁平化，只保留第一个属性映射的子节点（典型：`Statement`、`PortDecl`）
- **block_start / block_end**: 块规则，用于 `parse_block` 管理
- **atomic**: 原子规则，在解析器中有优先级排序（按 production 长度降序）
- **pratt**: 使用 Pratt 解析器处理表达式

### $N 路径语法

- `$1` — 引用第 1 个 production 元素的匹配结果
- `$2.sub_node[0]` — 索引访问
- `$3.items[*].sub_node[1]` — `[*]` 对整个列表做 map 操作
- N 不能超过 production 数组长度

### 语句分层（2026-06-28）

```
ModuleItem → DeclStmt | InstStmt | FuncStmt | AssignStatement | ProcStmt
Statement  → CtrlStmt | ProcAssignStmt | ProcLocalDecl | CallStmt
```

增强语法按层级精准挂载。详见 `rules_verilog/04_statements/`。

## EXT 增强语法层

`grammar/rules_verilog_ext/` — 与核心规则隔离，通过 production injection 在加载期挂载：

- 每个增强规则自声明 `[RuleName.inject] targets = ["@TargetRule"]`
- 支持**两层注入**（直接前置 + 传播到引用者）和 **replace**（替换 production / end_case）
- EXT 规则加载时必须使用 `cache_enabled=False` 强制重建缓存
- Parser / Renderer 不感知 transform 的存在

详见 `parser/grammar_inject.py`。

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

- `join` 原语默认包裹 `group()`，`SoftLine` 会被展平为空格；分隔符为 `\n` 时改用 `Break` 且不 group
- `SoftLine` 在 `group` 内 flat 模式变为空格，`Break` 不受影响
- `Nest` 会叠加——父级 body indent + 子级 join nest 可能产生多余空格
- `{ break = true }` 在 `line` 顶层会触发 `has_soft` 导致整行被 group 包裹
- `group` 在任一 ref 子表达式返回 None 时整体返回 None（防止空 range 渲染为 `[]`）

详见 [renderer_design.md](../../docs/renderer_design.md)、[config_reference.md](../../docs/config_reference.md)。

## SemanticAnalyzer

- 作用域由 TOML 中 `[RuleName.analyzer] scope = { name_attr, kind }` 声明
- 符号由 `symbol = { kind, name_attr }` 声明
- 标识符引用由 `identifier_ref = true` 声明
- **精简原则**：只做作用域管理 + 显式符号注册，不做隐式声明/常量折叠
- `Identifier` 节点沿作用域链查找，找到则附加 `_symbol_ref`

## Transform 引擎（后阶段）

`transform/post/` — 配置驱动的 AST 变换，用于类型展开等高级功能：

- **expand 原语**: `lookup` + `foreach` + `emit`，覆盖大多数场景
- **custom handler**: 复杂逻辑通过 `@transform_handler` 注册 Python handler
- **replace / delete**: 直接替换或删除节点
- 插件通过 `AstTransformer.register(plugin)` 注入，默认不含任何插件

详见 `transform/post/` 和 `grammar/rules_verilog_ext/` 中的 transform 配置示例。

## 可用 Skills

| Skill | 用途 | 调用 |
|-------|------|------|
| [grammar-lint](../../.github/skills/grammar-lint/SKILL.md) | TOML 语法规则静态检查 | `/grammar-lint` |
| [pipeline-debug](../../.github/skills/pipeline-debug/SKILL.md) | 管线故障排查（Token→AST→渲染） | `/pipeline-debug` |
| [renderer-debug](../../.github/skills/renderer-debug/SKILL.md) | 渲染布局问题追踪 | `/renderer-debug` |

已知问题速查：[debug_known_issues.md](../../docs/debug_known_issues.md)

## Git 提交约定

启用 `core.hooksPath` 后自动校验：
```
type(scope): description
# 示例: feat(parser): add for-loop support
```
允许的 type: `feat`, `fix`, `refactor`, `style`, `test`, `docs`, `chore`, `perf`, `ci`

## 测试

所有测试用例在 `verilog/ref/ref_*.v`，生成结果在 `verilog/gen/gen_*.v`。
全量回归：`python verilog/run_all_tests.py`（支持 `-v`、`--json` 参数）。
单用例：`python verilog/run_pipeline.py <test_name>`。
