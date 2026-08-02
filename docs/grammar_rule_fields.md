# 语法规则字段设计

> 状态: 已定稿（2026-08-01）
> 目标: 明确 GrammarRule 字段的语义、职责边界与正交度，收敛到最小复杂度
> 变更: 本次将 structure 展平、bound 更名 block、is_statement/is_block 转推导

## 设计哲学

**production 即真相（single source of truth）**：

- 配置作者只表达"语法是什么"（production），框架推导"怎么处理"。
- 保留的字段必须**职责唯一、正交、不可推导**——凡是能从 production 结构推导的信息，都不该让作者手写，否则手写标记与真实结构必然漂移（`ModuleDecl` 漏检即由此产生）。
- **不牺牲框架通用性**：推导逻辑基于通用的 production 结构特征，不绑定 Verilog。

## 字段分类总览

| 分类 | 字段 | 作者是否必写 |
|------|------|-------------|
| 本质 | `production` | ✅ 必写 |
| 本质 | `is_atom` | ✅ 必写（原子规则） |
| 本质 | `is_block` | ✅ 必写（块解析策略） |
| 语义边界 | `end_case` | 仅变长/歧义规则 |
| 增强 | `node` / `analyzer.*` / `renderer.*` | 可选 |
| 推导 | `block_start` / `block_end` / `is_statement` / `inline` | 不写（框架算） |
| 移除 | `structure` / `block = {start,end}` / `bound` 括号语义 / `[Rule.bound]` | — |

---

## 一、本质字段

### `production` — 语法结构本体

规则的生成式列表，是语法的唯一真相。

```toml
[AssignStmt.parser]
production = [
    "keyword.assign",
    "@PrimaryExpr",
    "symbol.base.equal",
    "@Expression",
    "symbol.base.semicolon",
]
```

- **消费方**: parser（规则匹配）、linter（语句检查器）
- **元素类型**: 字面 token（可含 `|` 候选）、子规则引用（`@Expression`）、后缀 `?`/`*`/`+`

### `is_atom` — 原子操作数解析策略（顶层 `[Rule]`）

标记"此规则可作为表达式操作数的原子"，供 pratt 解析器**原子优先结合**。

```toml
[Number]
is_atom = true

[ConcatExpr]
is_atom = true
```

- **消费方**: parser `parser_core.py` 的 `atomic_rules`（按 production 长度降序，作为 `atom_parser` 回调逐个尝试）
- **不可推导**: "哪些规则是表达式原子"是**语义决定**——`ConcatExpr`（`{a,b}`）、`SelectExpr`（`a[3:0]`）是复合结构（含变长 `@Expression`）却作为原子，production 结构无法区分，必须作者标注。

### `pratt` — 表达式处理标识（`[Rule.parser]`）

标记"此规则由 pratt 解析器处理"（运算符链 / 完整表达式，如 `Expression`、`UnaryExpr`、各级优先级规则）。**表达式根/黑盒按标识识别，不硬编码规则名**（`Expression`/`PrimaryExpr` 换语言即失效）：

- parser 走 `try_pratt_rule`；linter 视为**表达式黑盒**（lookahead 前缀路径在此截断，matcher 交 ExpressionChecker 完整 pratt 解析）。

```toml
[Expression.parser]
production = ["@PrimaryExpr|@UnaryExpr", "(@BinaryOp,@PrimaryExpr|@UnaryExpr)*"]
pratt = true
```

**原子入口（PrimaryExpr）不显式标记，由结构推导**：production 是纯 `@` 分派（choice of calls）且**全部分支都是 `is_atom` 规则**的选择器，即表达式原子入口（`PrimaryExpr = @BitWidthLiteral|@Number|@SelectExpr|@Identifier|...` 全为 `is_atom`）。`_is_atom_selector` 推导之，matcher 对其走 ExpressionChecker 原子匹配器——只匹配操作数、不消费运算符（解决 `a <= b` 赋值 vs 比较歧义）。

- **消费方**: parser `_production.py`（pratt 走 try_pratt_rule）；linter `lookahead.py`（pratt 黑盒截断前缀）、`checkers/matcher.py`（pratt→完整解析、`_is_atom_selector`→原子匹配）
- **区分理由**: `PrimaryExpr` 不能标 `pratt = true`——parser 会把它交给 pratt 解析（改变解析行为）；也不能标 `is_atom = true`——`is_atom` 会让 lookahead 展开 first tokens（破坏黑盒截断）、matcher 把普通原子也拉到 EC（实测 6 测试 FAIL）。原子入口由 `_is_atom_selector` 从 `is_atom` 结构推导，与 `is_atom` 正交（同一维度，无需独立字段）。

### `is_block` — 块解析策略（顶层 `[Rule]`）

标记"此规则走块解析路径"（消费 block 边界、body 内 newline 跳过逻辑、First set 跳过其内容）。

```toml
[Root]
is_block = true

[GenerateBlock]
is_block = true
```

- **消费方**: parser `_production.py`/`block_parser.py`/`rule_selector.py`（块匹配与边界）、linter `matcher.py`/`grammar_slicer.py`
- **不可推导**: 既有有 block 边界的块规则（`BeginEnd`/`ModuleDecl`），也有**无边界的纯块角色**（`Root` 文件容器）——后者 production 结构无法表达，必须作者标注。

---

## 二、语义边界字段

> `block = { start, end }` **已移除**（2026-08-01 重构）：块的起止 token 是语法结构本身，
> 直接写进 `production` 首尾（如 `ModuleDecl` 的 `keyword.module` / `keyword.endmodule`），
> 由框架在 `is_block` 时从 production 首尾字面 token 推导 `block_start` / `block_end`。

### `block_start` / `block_end` — 语法块边界（推导字段）

块规则的起止符配对，用于块解析与边界识别。**不手写**：`is_block = true` 时从 `production` 首尾字面 token 推导。

```toml
[ModuleDecl.parser]
production = [
    "keyword.module",        # ← 推导为 block_start
    "@Identifier",
    "@ParameterList?",
    "@PortParens?",
    "symbol.base.semicolon?",
    "keyword.endmodule",     # ← 推导为 block_end
]
```

- **消费方**: parser（块解析路径）、linter（发现器起始 token 注册、边界配对检查）
- **推导规则**: `is_block = true` 且 `production` 首元素是 `keyword.*` 字面 token → 首为 `block_start`、尾为 `block_end`；推导后从 `production` 剥离出"内容部分"（parser 块路径单独消费起止符，node 绑定 `$N` 基于内容部分，剥离后不变）
- **仅语法块**（`keyword.*` 边界）：括号配对不在此声明，统一走 `[bracket].pairs` 配置
- **不可推导**: `is_block` 本身（`Root` 等无边界块角色需作者标注）；但起止 token 完全由 production 表达，不再重复手写

### `end_case` — 变长/歧义规则的终止条件（`[Rule.parser]`）

规则匹配完成后，下一个 token 的预期集合；用于变长 production 的终止判定。

```toml
[Declarator.parser]
end_case = ["!symbol.base.dot"]   # 排除式：遇到 dot 不停止
```

- **消费方**: parser（规则边界）、linter（语句发现器的 `_statement_end`）
- **何时需要**: 变长 production（`*`/`+`/可选终止）或存在歧义时；定长 production 可省
- **不可推导**: `!` 排除语法、逗号列表终止等是语言手工微调

---

## 三、增强字段（可选，正交）

### `node` — 属性绑定（`[Rule.parser.node]`）

从生产式消费位置提取 AST 节点属性（`$1`/`$2` 引用）。

### `analyzer.*` / `renderer.*` — 语义/渲染配置

各自领域的配置，与语法结构正交。

---

## 四、框架字段（is_statement 显式标记 / inline 推导）

### `is_statement` — 显式标记（语句规则开关）

每个语句规则直接标记 `is_statement = true`，框架不再推导：

```toml
[BlockingAssign]
is_statement = true
```

- **语义**: 该规则是一条可发现的"句子"（模块级或过程体语句）。parser 顶层
  `statement_rule_names`、linter 发现/消歧/检查均消费此字段。
- **入口选择器**（`Stmt`/`TaskStmt`/`ModuleItem`）：保留 `statement_entry = true` 仅作
  "语句分发入口"的语义标识，**不标** `is_statement`（选择器不是句子；标了会导致
  linter 消歧表与 parser 候选出现冗余注册）。
- **块语句**（`ModuleDecl`/`FuncDecl`/`TaskDecl`/`BeginEnd`/`GenerateBlock` 等）同样显式
  标 `is_statement = true`（与 `is_block = true` 并列）。
- **上下文归属**：linter 的 B 类 ident 候选按模块/过程上下文分组，由
  `lookahead._context_leaves` 从入口选择器沿纯 `@` 分派展开（结构遍历，与
  `is_statement` 无关）。

### `inline` — 选择器规则自动展平

production 是纯 choice of calls（如 `CtrlStmt`、`PrimaryExpr`）→ 自动内联展平。

---

## 五、本次变更（从旧字段迁移）

| 旧字段 | 新状态 | 说明 |
|--------|--------|------|
| `structure = { is_atom = true }` | `[Rule] is_atom = true` | 展平到顶层 |
| `structure = { is_block = true }` | `[Rule] is_block = true` | 展平到顶层 |
| `structure = { is_statement = true }` | `[Rule] is_statement = true` | 显式标记，无推导 |
| `bound = { start, end }`（语法块） | 删除 | 起止 token 写回 `production` 首尾，由 `is_block` 推导 `block_start/end` |
| `bound = { start, end }`（括号配对） | 删除 | 走 `[bracket].pairs` |
| `[Rule.bound]` 顶层 table | 删除 | 单一写法 |
| `block = { start, end }` | 删除 | 同 bound 处理，production 推导 |
| `structure` 字段本身 | 删除 | 展平为顶层标记 |

---

## 相关

- `core/define.py` — GrammarRule 字段定义
- `parser/parser_core.py` — `atomic_rules` 原子优先结合、`statement_rule_names` 候选
- `parser/rule_selector.py` — First set / 候选过滤
- `linter/lookahead.py` — 语句发现消歧表（消费 is_statement、block.start）
- `docs/end_case_audit.md` — end_case 严格度审计
