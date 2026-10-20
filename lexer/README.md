# lexer — 词法（token 定义驱动扫描）

> 文本 → Token 流。token 类型/符号/字符串/注释/数字形态全由 `grammar/` TOML
> 声明（`base/_token.toml` + `[lexer]` 段），本包不硬编码语言知识。

| 文件 | 一句话 |
|------|--------|
| `main_lexer.py` | Lexer 主扫描器（token 定义驱动 + 行状态/缩进单位锁定） |
| `capture_runner.py` | 配置驱动原始文本捕获（注释/字符串/块标量 token） |
| `number_gen.py` | 数字形态声明（`[[number.based]]`）→ FSM 转移表 |
| `number_runner.py` | 配置驱动数字解析（唯一路径） |
| `pre_scan.py` | 轻量预扫描（顶层声明符号收集） |
| `lexer_utils.py` | TOML 配置加载与合并工具 |

> 入口：`Lexer.tokenize`；缩进相关（YAML）看 `[indent]` 配置与 `_indent_unit`。

## `[string]` 声明字段（`base/_token.toml`）

| 键 | 语义 |
|---|---|
| `delimiters` | 定界符列表（C 的 `"` 与 `'`；verilog 只有 `"`）——每个定界符一条 delim 捕获规则，`token_type = "literal.string"` |
| `escape` | 段内转义字符（单字符，可选）：`\X` 整体并入内容、不参与终止判定；不声明 = 无转义语义 |
| `prefixes` | 字面量**前缀**表（`前缀 → 允许的定界符列表`，可选）：每组合一条 `start = 前缀+定界符` 的捕获规则 ⇒ 前缀是 token 的一部分（`u8"x"` / `L'x'` 单 token、内容含前缀、渲染原样输出）；前缀与定界符必须紧邻；**不声明 = 无前缀语义** |

- 前缀**按档位声明**：C 包的 `L` 在核心基线（C99），`u`/`U`/`u8` 字符串在 c11 插件、
  `u8` 字符在 c23 插件（插件 `token_ext` 的同名键深合并覆盖，见
  `grammar/c/plugins/{c11,c23}/_token_ext.toml`）——引擎只读声明，不做语言判断。

## `[[number.based]]` 声明字段（`base/_number.toml`）

| 键 | 语义 | 消费方 |
|---|---|---|
| `name` / `size` / `base_prefix` / `bases` / `value_digits` / `value_allow` / `value_allow_space` | 形态本体（size→base→value 链） | `number_gen.compile_number_pattern` |
| `suffix = { chars, max }` | 字面量**尾随后缀**（C 的 `42u` / `1.5f`）：DFA 之后的声明式尾段，由 runner 在接受位后消费 | `number_runner._consume_suffix` |
| `lead_dot = true` | 该形态额外接受**以小数点开头**的浮点（C 的 `.5`）：点后至少一位数字，`.` 本身仍归符号表 | `number_gen.build_lead_dot` + `number_runner.starts_at_declared_non_digit` |
| `lead_sign = true` | 该形态额外接受**以符号开头**的数（yaml 的 `-5` / `+5` / `-0.5`）：符号后至少一位数字，裸 `-` 仍归符号表（序列指示符 `- 8080` 不被劫持） | 同上（`build_lead_sign`） |
| `digit_separator = "'"` | 数字序列内的**分隔符**（C23 的 `1'000` / `0x1'F`）：编译期在每个数字自环态旁挂分隔态（`S --sep--> S'` 非接受、`S' --digit--> S`），故必须夹在数字之间；尾随 `1'` / 连续 `1''0` 不并入 | `number_gen._expand_digit_separator` |

- 两个前导键（`lead_dot` / `lead_sign`）都要求 **无前缀**形态，且**不可同时声明**
  （各是独立前导子图，组合形态 `-.5` 未支持）——声明违规即 fail-fast（ConfigError）。
- 前导键必须在词法层：换行/空格是 trivia，`key: -5` 与 `seq:` 换行后的 `- 8080`
  化简为同一 token 对，语法层拿不到"符号与数字是否相邻"；实测语法侧方案会把
  `seq:\n- 8080` 吞成 `seq: -8080`。
- 未声明前导键的形态零变化（裁决点：`starts_at_declared_non_digit` 只放行**显式
  表态**的形态，防同字符符号被劫持）。
- `digit_separator` 同样**按档位声明**：C 的 `'` 只在 c23 插件的 `_number_c23.toml`
  里声明（基线/c11 不声明 ⇒ `1'000` 仍切成 `1` + 字符常量），故档位 = 接受域由声明面
  组合决定；位置合法性（`0x'1` / `1.'5`）不在词法层判，核同 `1ff` 的宽进口径。
