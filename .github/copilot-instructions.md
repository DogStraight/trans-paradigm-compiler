# PyV Compiler — 项目约定

## ⚠️ Agent 行为准则（最高优先级）

**禁止事项：**
- ❌ **绝不 `pip install` 任何包** — 项目零外部依赖，只用 Python 3.11+ 标准库
- ❌ **绝不在 Python 代码中硬编码 Verilog 专用逻辑** — 所有语言行为由 TOML 配置驱动
- ❌ **不要修改管线顺序** — Lexer → Parser → Normalizer → SemanticAnalyzer → Renderer 不可颠倒
- ❌ **不要引入新的配置文件格式** — 只使用 TOML

**必须遵守：**
- ✅ 新增语法特性 → 优先改 TOML 规则文件，改不动了再动引擎代码
- ✅ 修改 ≥ 3 个文件时，先想能不能减少到 1-2 个
- ✅ 每次修改后运行 `python verilog/run_all_tests.py` 确认全量回归通过
- ✅ 新语法特性 = 新 `verilog/ref/ref_*.v` 测试用例

## 项目概述

配置驱动的 Verilog 编译框架（纯 Python 3.11+，零外部依赖）。
**本质硬编码保留在代码中，偶然硬编码全部配置化**。详见 [README](../../README.md) 和 [ROADMAP.md](../../ROADMAP.md)。

## 项目哲学与架构约束

### 硬编码阈值（最核心原则）

| 可硬编码（语言通用） | 不可硬编码（语言专用） |
|---------------------|----------------------|
| id / number / string / comment | module / wire / always / function |
| newline / space / symbol / operator | typedef / Declarator / PortTail |
| open_bracket / close_bracket | end_case / rule_hints / 类型系统 |

判断标准：**这个概念是否在任何编程语言中都存在？** 是 → 可硬编码；否 → 必须 TOML 配置化。

### 三阶配置化

| 层级 | 方式 | 示例 |
|------|------|------|
| 核心引擎 | Python，零外部依赖 | main_parser.py, renderer.py |
| 语法规则 | TOML production + layout | _token.toml, 00_blocks.toml |
| 元能力 | EXT 注入 + transform 原语 | rules_verilog_ext/, transform/post/ |

每层严格单向依赖：TOML → Python，不反向。

### 已确定的架构决策（不再争论）

- 递归下降 + 回溯（非生成式解析器）
- Pratt 表达式解析（声明式优先级 via `_symbol_level.toml`）
- Doc IR 渲染（Wadler-Lindig 算法）
- EXT 注入（非继承/覆写）
- 预扫描符号表（非 parser 内联语义分析）
- 单 TOML 格式（非多格式混用）
- 零外部依赖（非 PyPI 包）
- 不写单元测试 — E2E 覆盖 + 快速反馈循环更有效

### 命名约定

- Python: `snake_case`（函数/变量/方法）
- 节点类型/规则名: `PascalCase`（`Declarator`, `ModuleInst`）
- 私有: `_prefix`（`_match_productions`, `_CACHE`）
- 常量/枚举: `UPPER_CASE`（`LOG_INFO`, `_ORDER_NOT_FOUND`）

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
python main.py pipeline [test_name]                   # CLI 入口
python verilog/run_pipeline.py [test_name]             # 直接运行（默认 normal/ref_led_blinker）
python verilog/run_pipeline.py [group] [test_name]    # 指定组+用例，如 normal counter
python verilog/run_pipeline.py --debug                 # 调试模式（输出调试信息）
python verilog/run_pipeline.py --inline-comments       # 内联注释指纹回注
python verilog/run_pipeline.py --expand-macros         # 宏展开
python verilog/run_all_tests.py                        # 全量回归
python verilog/run_all_tests.py -v                     # 详细输出
python verilog/run_all_tests.py --json                 # JSON 报告（输出到 test_report.json）
python verilog/run_all_tests.py normal                 # 仅 normal 组
python verilog/run_all_tests.py errors                 # 仅 errors 组
python verilog/run_all_tests.py normal counter         # 仅单个用例
python verilog/run_all_tests.py --expand-macros        # 展开宏后再测试
```

`run_pipeline.py` 查找顺序：`normal/<test_name>` → `errors/<test_name>`。
`run_all_tests.py` 支持 `normal` / `errors` 分组过滤和子串匹配筛选。

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

## 调试快速参考

### 常见失败模式速查

| 现象 | 可能原因 | 排查方向 |
|------|---------|---------|
| 生成代码完全为空 | parser 返回 Root 仅 1 节点 | 检查 Token 流 + 候选规则匹配 |
| `所有候选规则匹配失败: '...'` | 语句级规则过滤条件错误 | 检查 `end_case` 是否为空列表 |
| 注释与代码合并到同一行 | `join` 的 `SoftLine` 被 group flat 展平 | `\n` 分隔符改用 `Break` 且不 group |
| 缩进错位/多余空格 | `Nest` 叠加效应 | 检查父级 body indent + 子级 join nest |
| 端口 `)` 不在独立行 | 软换行被 group flat 模式吞掉 | 添加 `{ soft = true }` 或 `{ break = true }` |
| 模块实例端口缩进偏移 | `join nest` 与父 `body indent` 叠加 | 移除子级 nest |
| 数字/字面量渲染为空 | `extract_value.names` 未覆盖该 literal 类型 | 在 `normalize_config.toml` 中添加 |

详见 [debug_known_issues.md](../../docs/debug_known_issues.md) 和 [design_lessons.md](../../docs/design_lessons.md)。

### 调试工作流

1. **解析失败** → 用 `/pipeline-debug` skill 追踪 Token→AST
2. **渲染布局异常** → 用 `/renderer-debug` skill 追踪 Doc IR
3. **TOML 规则配置错误** → 用 `/grammar-lint` skill 静态检查
4. **AST 结构异常** → 输出 AST JSON（`verilog/ast/*.json`），对照 [ast_normalization.md](../../docs/ast_normalization.md) 检查规范形式

## 可用 Skills

### Workspace Skills

| Skill | 用途 | 触发方式 |
|-------|------|---------|
| grammar-lint | TOML 语法规则静态检查 | `/grammar-lint` |
| pipeline-debug | 管线故障排查（Token→AST→渲染） | `/pipeline-debug` |
| renderer-debug | 渲染布局问题追踪 | `/renderer-debug` |

### User-level Skills（`c:\Users\micro\.agents\skills\`）

| Skill | 用途 | 触发方式 |
|-------|------|---------|
| grammar-extension | 语法扩展工作流：从 TOML 规则到测试验证 | `/grammar-extension` |
| hardcode-check | 检查魔法数字/重复逻辑/硬编码路径 | `/hardcode-check` |
| project-research | 调研外部项目，评估对 PyV 的参考价值 | `/project-research` |
| pwsh-cookbook | PowerShell 脚本编写参考（转义/编码/hook） | `/pwsh-cookbook` |

## Session Summary Hook

每次新对话时，`UserPromptSubmit` hook 自动运行 `.github/hooks/scripts/load-summary.ps1`，加载 `.github/session-summary.md` 注入上下文。

- 配置在 `.github/hooks/session-summary.json` 中
- `post-commit` Git hook 自动更新 session-summary（日期 + HEAD SHA）
- 让新对话快速接入上次进展

## Git 提交约定

启用 `core.hooksPath` 后自动校验（`.github/hooks/git/`）：
```
type(scope): description
# 示例: feat(parser): add for-loop support
```

### Git Hooks

| Hook | 用途 |
|------|------|
| `commit-msg` | 验证提交信息格式 `type(scope): description` |
| `pre-commit` | 检查 `linter/` 代码中是否有硬编码语言知识（Verilog 专用 token、中文消息等） |
| `post-commit` | 自动更新 `.github/session-summary.md`（日期 + HEAD SHA） |

启用方式：
```bash
git config core.hooksPath .github/hooks/git
```

允许的 type: `feat`, `fix`, `refactor`, `style`, `test`, `docs`, `chore`, `perf`, `ci`

详见 `.github/hooks/git/README.md`。

## 测试

### 测试目录结构

```
verilog/tests/
├── normal/         — 正常用例（预期解析成功）
│   ├── ref/       — 参考输入 .v 文件
│   ├── gen/       — 自动生成 .v 文件
│   ├── ast/       — AST JSON 快照
│   ├── lex/       — Token 流快照
│   └── symbols/   — 符号表快照
└── errors/        — 错误用例（预期解析失败）
    ├── ref/ / gen/ / ast/ / lex/
```

### 命令

```bash
python verilog/run_all_tests.py              # 全量回归
python verilog/run_all_tests.py -v           # 详细输出
python verilog/run_all_tests.py --json       # JSON 报告（test_report.json）
python verilog/run_all_tests.py normal       # 仅 normal 组
python verilog/run_all_tests.py errors       # 仅 errors 组
python verilog/run_all_tests.py counter      # 子串匹配筛选
python verilog/run_pipeline.py counter       # 单用例
python verilog/run_pipeline.py --debug       # 调试模式
```

- 新语法特性 = 新 `verilog/ref/ref_*.v` 测试用例
- 生成结果在 `verilog/gen/gen_*.v`，与参考文件对比行数和状态
- 目标：全量回归 < 1s，32 测试 → 300 测试 < 10s

## 预处理器（`preprocessor/`）

- 独立阶段，插在 Lexer 前执行
- 当前支持：`` `define `` 宏展开 + 逆向还原
- 入口：`preprocessor.preprocess()` / `preprocessor.protect_and_reverse()`
- 使用 `--expand-macros` 开关启用
- TOML 配置：`grammar/rules_verilog/base/_macro.toml`

## 关键文档索引

| 文档 | 内容 | 何时查阅 |
|------|------|---------|
| [coding_style.md](../../docs/coding_style.md) | 代码注释/命名/布局规范 | 编写新代码或审查风格时 |
| [ROADMAP](../../ROADMAP.md) | 架构决策、设计哲学、非目标 | 理解"为什么不那样做" |
| [docs/grammar.md](../../docs/grammar.md) | AST 节点类型图谱（Mermaid） | 了解有哪些节点类型 |
| [docs/ast_normalization.md](../../docs/ast_normalization.md) | 规范化后的规范 AST 结构 | 写 Renderer/Transform 时 |
| [docs/renderer_design.md](../../docs/renderer_design.md) | Doc IR 架构与 DSL 原语 | 调试渲染布局问题 |
| [docs/config_reference.md](../../docs/config_reference.md) | 所有 TOML 参数参考表 | 写 TOML 规则时查参数 |
| [docs/debug_known_issues.md](../../docs/debug_known_issues.md) | 已知问题速查表 | 遇到眼熟的问题时 |
| [docs/design_lessons.md](../../docs/design_lessons.md) | 语义级 bug 与架构教训 | 避免重蹈覆辙 |
| [docs/layout_spacing_prompt.md](../../docs/layout_spacing_prompt.md) | 布局间距设计提示 | 处理缩进/空行问题 |
| [docs/references.md](../../docs/references.md) | 外部项目对比与参考 | 调研/设计决策时查阅 |
| [TODO.md](../../TODO.md) | 当前待办事项 | 找下一个任务 |
