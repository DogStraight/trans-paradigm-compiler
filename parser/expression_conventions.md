# 表达式系统隐式约定

> 文档目的：列出表达式系统（Pratt + `is_atom` + `[[operator]]`）的全部隐式规则，
> 避免新语言作者/模型从零猜协议。来源：2026-08-12 c4 过程反思。

## 1. 优先级 = `[[operator]]` 数组顺序（低 → 高）

```
grammar/verilog/base/_symbol_level.toml

[[operator]]   # 最低优先级（第一个）
symbol = "?"
arity = 3
second = ":"
assoc = "right"

[[operator]]   # 次低
symbol = "or"
arity = 2
assoc = "left"

...            # 越往后优先级越高

[[operator]]   # 最高优先级（最后一个）
symbol = "*"
arity = 2
assoc = "left"
```

**隐式规则**：`operator` 数组**顺序即优先级**——位置越靠前优先级越低。
新增运算符 = 在合适位置插一个 `[[operator]]`，**不写优先级数字**。

## 2. `is_atom` 规则：atom 是表达式的最小单元

```
[PrimaryExpr.parser]  # 或类似的 atom 规则
production = [
    "@Number|@StringLiteral|@SelectExpr|@Identifier|...",
]
```

**隐式规则**：`is_atom` 规则的 production 里，**长 production 优先匹配**
（选择器从长到短尝试）。例如 `@SelectExpr`（`a[3:0]`）先于 `@Identifier`（`a`）——
否则 `a[3:0]` 会被 `@Identifier` 吃掉 `a` 然后 `[3:0]` 报错。

## 3. 三元运算符 `? :`

```
[[operator]]
symbol = "?"
arity = 3
second = ":"
assoc = "right"
```

**隐式规则**：
- `arity = 3` 表示三目（`cond ? a : b`）。
- `second = ":"` 指定第二分隔符（`?` 是主符号，`:` 是 second）。
- 三目的中值 `a` 是**完整表达式**（不是受限的）。

## 4. 一元 vs 二元同符号：`position` 区分

同一符号既是一元又是二元（如 `-`、`!`）时：

```
# 一元（前缀）——position = "prefix"
[[operator]]
symbol = "-"
arity = 1
position = "prefix"

# 二元（中缀）——无 position（默认 infix）
[[operator]]
symbol = "-"
arity = 2
assoc = "left"
```

**隐式规则**：`position = "prefix"` 声明一元（前缀），无 position 是二元（中缀）。
同符号两种声明并存，Pratt 按上下文（前有操作数 → 中缀，否则 → 前缀）选择。

## 5. 关联性

- `assoc = "left"`：`a - b - c` = `(a - b) - c`
- `assoc = "right"`：`a = b = c` = `a = (b = c)`
- **缺省 = 左结合**（不写 assoc 即 left）。

## 6. 符号 token 定义分离

运算符的**词法形态**（token 识别）在 `_symbol_level.toml` 的 `[symbol]` 段或
`_token.toml`，运算符的**语法语义**（优先级/结合性）在 `[[operator]]`。
两者通过 `symbol` 字段对应：

```
[symbol]           # 词法：识别这个符号
double_plus = "+"

[[operator]]       # 语法：这个符号的优先级/结合性
symbol = "+"
arity = 2
assoc = "left"
```

## 7. `pratt_level`：pratt 入口的优先级上限

```
[UnaryLevelExpr.parser]
pratt = true
pratt_level = "unary"        # "expression"（默认，吃全部中缀）/ "unary"（只到一元层级）
production = ["@PrimaryExpr"]  # FIRST 集种子
```

**隐式规则**：`pratt = true` 的规则被引用时默认从 `rbp=0` 起（吃全部中缀）；
声明 `pratt_level = "unary"` 则从 `max_infix_prio` 起 —— 中缀循环的准入条件是优先级
**严格大于** rbp，故一元层级**不吃任何中缀**，只留原子 / 前缀 / 后缀。

**用途**：操作数不该吞中缀的位点。典型（C 包首例）：
- `sizeof unary-expression` —— 否则 `sizeof a * b` 被解析成 `sizeof (a*b)`；
- `( type-name ) cast-expression` —— 否则 `(int)x * y` 被解析成 `(int)(x * y)`。

**前缀一元不受影响**：`_parse_prefix_unary` 自带 `unary_prefix_rbp`，故 `sizeof *p` /
`(unsigned)-1` 照常可用。

取值非法（除 `"expression"` / `"unary"` 之外）→ parser 侧 **ConfigError**（fail-fast，
不静默降级成默认层级）。

## 8. 常见坑

| 坑 | 现象 | 修法 |
|---|---|---|
| 运算符顺序错 | `a + b * c` 解析成 `(a+b)*c` | 把 `*` 移到 `+` 之后（更高优先级） |
| atom 短 production 在前 | `a[3:0]` 被吃成 `a` + 报错 | atom production 长规则在前 |
| 三目忘 second | `? :` 只认 `?`，`:` 报错 | `arity=3` + `second=":"` |
| 一元忘 position | `-a` 解析失败 | 一元声明加 `position="prefix"` |
| 操作数吞中缀 | `sizeof a * b` → `sizeof (a*b)` | 操作数位点用 `pratt_level = "unary"` 的入口规则 |
| 逗号进运算符表 | 实参/初始化器/枚举项分隔被吞（枚举体 3 项塌成 1 项） | 逗号走**语法形态**（C 包 `CommaExpr`），不进表 |

## 评估结论（2026-08-13）

- 机制保持（数组顺序 = 优先级是最简表达，优于显式数字——避免优先级数字不一致）。
- 本文档作为"表达式系统隐式约定清单"，walkthrough 补一节引用本文档。
