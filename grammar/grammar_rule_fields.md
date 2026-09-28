# 语法规则字段设计

> 本文档描述 GrammarRule 字段的**现有结构**（语义/职责边界/正交度，最小复杂度）。
> 设计哲学见下；权威字段定义在 `core/define.py`。

## 设计哲学

**production 即真相（single source of truth）**：

- 配置作者只表达"语法是什么"（production），框架推导"怎么处理"。
- 保留的字段必须**职责唯一、正交、不可推导**——凡是能从 production 结构推导的信息，都不该让作者手写，否则手写标记与真实结构必然漂移（`ModuleDecl` 漏检即由此产生）。
- **不牺牲框架通用性**：推导逻辑基于通用的 production 结构特征，不绑定 Verilog。

## 字段分类总览

| 分类 | 字段 | 作者是否必写 |
|------|------|-------------|
| 本质 | `production` | ✅ 必写 |
| 本质 | `is_atom` / `is_block` | ✅ 必写（解析策略标注） |
| 本质 | `pratt`（`[Rule.parser]`） | 表达式规则标注 |
| 语义边界 | `exclude` | 仅消歧规则（负向前瞻） |
| 框架标记 | `is_statement` | 语句规则显式标 true |
| 增强 | `node` / `analyzer.*` / `renderer.*` | 可选 |
| 推导（不写） | `inline` / FOLLOW | 框架算 |

> 已移除的历史字段（`structure` / `bound` / `block = {start,end}` / `end_case`）
> 不再出现——见正文各处「已移除」注记。

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

production 串是**微语法**（EBNF 变体），拼写规则如下：

| 语义 | 写法 | 例 |
|------|------|-----|
| 序列 | **逗号 `,`** | `"keyword.assign,@Identifier,symbol.base.equal"` |
| 选择 | `\|` | `"@Stmt\|symbol.base.semicolon"` |
| 可选 | 后缀 `?` | `"@BlockLabel?"` |
| 重复 | 后缀 `*`（0+）/ `+`（1+） | `"(...)*"` |
| 分组 | `(...)`（内部用 `\|` 或 `,`） | `"(keyword.assign\|keyword.force)"` |
| 规则调用 | `@Rule` | `@Expression` |
| 字面 token | `keyword.xxx` / `symbol.base.xxx` | `keyword.fork` |

⚠ **序列必须用逗号，不能用空格**：`build_tree` 第一步就是 `replace(" ", "")`
（`parser/rule_selector.py`），空格会被删掉、相邻元素粘成一个。实测两种后果：

| 写法 | 结果 |
|------|------|
| `"keyword.assign keyword.force"` | 静默变成**单个 token** `keyword.assignkeyword.force`（不存在 → 该候选永不匹配，最难查） |
| `"@Decl @Decl"` | `GrammarError: 无效的产生式片段: @Decl@Decl`（粘连后不成 token 形态） |

正确：`"keyword.assign,keyword.force"` / `"(keyword.assign,keyword.force)?"`。逗号后的空格
无害（会被删掉）；只有**用空格代替逗号**才是错。

#### 空产生式 `production = []` — 两种含义

| 规则形态 | 含义 | 注入落点 |
|---|---|---|
| **块规则**（`is_block = true`） | 形态由块机制驱动（`block_start`/`block_end`/`block_prods`），无独有 production | 无处可落（`inject` 保持 no-op） |
| **非块规则** | **空槽位**：无自有形态的共用扩展点位 | 注入即成为它**唯一的元素**（越界 append 的零长特例） |

空槽位的用法（样板见 `grammar/c/01_declarations.toml` §`AttributeSlot`）：宿主把槽位写成
`@Slot*` / `@Slot?`，增量插件 `targets = ["@Slot.production[0]"]` 往里注规则——于是
**"往宿主序列中段插元素"变成"给一条规则加形态"**，既不必改宿主、也不依赖跨元素回溯。

- `node` 绑定对空槽位允许 `$1`（指注入后填入的那个元素）——这是唯一的越界例外，
  实现在 `core/define.py::_check_pos_ref`（`empty_slot` 参数）。
- 注入语义见 `parser/grammar_inject.py::_inject_direct`；空槽位自身常用
  `inline = true` + 单字段 `node`，使其不进 AST（父节点直接拿到槽里的节点）。

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

**原子入口（PrimaryExpr）不显式标记，由结构推导**：production 是纯 `@` 分派（choice of calls）且**全部分支都是 `is_atom` 规则**的选择器，即表达式原子入口（`PrimaryExpr = @Number|@SelectExpr|@Identifier|...` 全为 `is_atom`）。`_is_atom_selector` 推导之，matcher 对其走 ExpressionChecker 原子匹配器——只匹配操作数、不消费运算符（解决 `a <= b` 赋值 vs 比较歧义）。

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

### 边界后继（已移除 `end_case`）— 派生 FOLLOW + `exclude`

规则的后继合法性由引擎从 production 结构**机械推导**（parser/follow.py 的
FOLLOW 集，对标 yacc 派生）：规则匹配完后，当前 token ∉ FOLLOW → 拒绝回退。
语法是唯一真相源，无需手写后继 token 集合（旧 `end_case` 字段已移除）。

```toml
[Declarator.parser]
exclude = ["symbol.base.dot"]   # 负向前瞻：匹配后若后跟 . 即失败回退
```

- **`exclude`**（`[Rule.parser]`，列表）— 负向前瞻（非 FOLLOW 数据）：声明器
  匹配后遇此 token 即失败回退。用途：消歧——如 `@DeclaratorList` 的 repeat
  贪吃逗号分隔项时，`spi.slave` 类型引用的 `.` 应阻止 Declarator 吞掉类型
  引用（`input rstn, spi.slave ...` 中 `spi` 不能当第二个 declarator）。该歧义
  是 Declarator 自身语法不可推导的（FOLLOW 不含 `.`，但无歧义时 `.` 也应
  拒绝），故独立字段声明，parser 与 linter 共同消费。
- **消费方**: parser（`try_plain_rule` 的 exclude 负向前瞻——匹配成功后、FOLLOW
  检查前，下一个非 trivia token 命中 exclude 即整体回退）、linter
  （`_statement_end` 从 production 推导句子边界）
- **与 FOLLOW 的关系**: exclude 必须**先于** FOLLOW 检查——派生 FOLLOW 会注入
  pratt 运算符家族前缀（`symbol.base.`），家族成员（如 `.`）会被
  `token_in_follow` 前缀匹配误放行；exclude 是显式拒绝（严格），FOLLOW 是
  后继集合（宽松），二者正交
- **不需要手写**: 逗号列表、分号、右括号等后继全部由 FOLLOW 推导；`exclude`
  只用于"显式拒绝某 token"的消歧场景

#### FOLLOW 传播范围（嵌套元素内部已递归；仍有的旁路）

- **递归到嵌套元素内部**：推导不只是扫规则顶层的 production 元素列表，而是按
  元素树结构递归——**choice 备选支 / `(...)` 括号分组 / `?` `*` `+` 后缀组的内部
  seq** 里，`@call` 同层的后续兄弟 FIRST 都会进它的 FOLLOW。实测：
  `production = ["(@X,lit.tail)|(@Y,lit.tail2)"]` ⇒ `FOLLOW(X) ⊇ {lit.tail}`；
  `["(bracket.l_square_bracket,@Expression,bracket.r_square_bracket)+"]` ⇒
  `FOLLOW(Expression) ⊇ {bracket.r_square_bracket}`。故"多备选写全序列""组内序列"
  都是正常写法，无需为了 FOLLOW 把序列拆到列表层级（判据见
  `tests/engine/parser/test_follow.py::TestNestedSeqTailPropagation`）。
- **方向是只增不减（fail-open）**：传播取"元素级（原口径，含过度包含）+ 结构级
  （递归精确）"的并集，只会让 FOLLOW 变大 ⇒ **FOLLOW 检查这一关不会新增拒绝**
  （原先被误拒的形态转为可继续）；分支选择仍可能因放宽而变化，由回归用例覆盖。
  实现见 `parser/follow.py::_propagate_seq` / `_propagate_intra`。
- **仍不覆盖的旁路**（不是缺陷，是分层事实，使用前需知道）：
  1. **pratt 规则不做 FOLLOW 检查**——`_try_pratt_rule` 分支直接返回，不经
     `check_end_case`；`Expression` 这类 pratt 规则自身的 FOLLOW 缺项**不产生
     症状**，真正受检的是它下游的 atom 规则（`Identifier` / `Number` / `CallExpr` …）。
  2. **`_prod_refs_block` 旁路**：production 直接引用块规则的规则跳过 FOLLOW
     检查（块边界由结构决定）。
  3. FOLLOW 是**静态下界**：从 production 结构推导，不模拟运行期回溯 / 最长匹配 /
     `exclude` / pratt；`token_in_follow` 对 `symbol.base.` 这类**前缀族**是
     fail-open 放行整族。

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
- **入口选择器**（`Stmt`/`TaskStmt`/`ModuleItem` 等纯 @ 分派选择器）：**不标**
  `is_statement`（选择器不是句子；标了会导致 linter 消歧表与 parser 候选出现
  冗余注册）。语句发现从 is_statement 规则 + block_start 结构自推导，无需任何
  入口角色字段（原 `statement_entry` 角色值/`[linter]` 集中配置已删除）。
- **块语句**（`ModuleDecl`/`FuncDecl`/`TaskDecl`/`BeginEnd`/`GenerateBlock` 等）同样显式
  标 `is_statement = true`（与 `is_block = true` 并列）。块体上下文无需声明
  （原 `body_context`/`opener_context` 已删除——context 不参与候选筛选）。
- **消歧**：linter 的 B 类 ident 候选注册到**单一全局集合**（不按上下文分组），
  靠 Level 1 变长前瞻/Level 2 试解析精确筛选。

### `inline` — 选择器规则自动展平

production 是纯 choice of calls（如 `CtrlStmt`、`PrimaryExpr`）→ 自动内联展平。

---

## 相关

- `core/define.py` — GrammarRule 字段定义
- `parser/parser_core.py` — `atomic_rules` 原子优先结合、`statement_rule_names` 候选
- `parser/rule_selector.py` — First set / 候选过滤
- `linter/lookahead.py` — 语句发现消歧表（消费 is_statement、block.start）
- `parser/follow.py` — 派生 FOLLOW（end_case 移除后的后继合法性推导）
