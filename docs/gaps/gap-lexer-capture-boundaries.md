# Gap — lexer 捕获边界（多字符定界符 / 块标量折叠 / 触发条件）

- 状态：**立项中**（TODO「缺口闭环队列」①，2026-09-12 排队）：先补 `delim`
  单字符 fail-fast，再做定界符序列；块标量折叠/触发谓词仍为未立项扩展
- 关联：原 `docs/known_limitations.md` Architecture 边界（2026-09-04 按部件拆入本档）
- 参照：YAML 块标量（`|`/`>`）语义、Rust 原始字符串 `r#"`（IEEE/规范源）

## 缺口是什么

`lexer/capture_runner.py`（CaptureRunner 原语）捕获原文直到行尾/字面标记/
整行匹配/闭合定界符/列比较（`indent_leq`——YAML 块标量 `|`/`>` 在内容缩进
≤ 触发行时终止）。注释/字符串/heredoc/fenced 块/块标量均配置声明
（`[comment] pairs`、`[string] delimiters`、`[[capture]]` 含可选
`after`/`next_chars` 触发）。三个具体缺口：

1. **`delim` 类定界符限单字符**（`"`/`'`）：多字符定界符（`"""`）需定界符
   序列扩展。实测（2026-09-12）：`marker`/`line_match` 类已用
   `text[pos:pos+end_len]` 支持多字符 `end`，**唯 `delim` 类**的终止判定是
   `ch == rule.end`（单字符比较）——配 `"""` 会**静默**永不终止（退化为"到
   行尾"，不报错）。这同时是 fail-fast 缺口：要么实现定界符序列（含起止
   不同的 `r#"` 形态需扩 `CaptureRule`），要么先在 `build_rules` 加"delim 须
   单字符"校验堵住静默路径。
2. **块标量内容原样捕获**：折叠（`>`）、chomping（`-`/`+`）、缩进指示符被
   保留但不做语义展开；指示符行注释随 token 一起带走。
3. **触发条件限声明式二元组**：prev-token-in-set + next-char-in-set 对，
   更丰富的上下文谓词需另一机制。

## 为什么是缺口（影响面）

yaml 语言包（块标量）与未来带多字符字符串定界符的语言受影响；折叠/chomping
不语义化让 yaml 往返保真依赖"保留原样"而非"正确语义重排"。

## 成熟解法参照（见贤思齐）

- YAML 规范对 `>` 折叠与 `-`/`+` chomping 有精确语义——直接借鉴其折叠规则。
- Rust/Python 多字符原始字符串定界符是"定界符序列"的成熟解法。

## 可实现性

- 定界符序列：capture 配置加"定界符序列"表，扫描做最长匹配。
- 折叠/chomping：捕获后按 YAML 语义后处理（折叠空格/保留尾行）。
- 触发谓词：capture 触发条件从声明式对扩展为（保留声明式兜底）低优先级。
- 验证：yaml/c4 语言包测试 + 往返保真门禁。
- 当前依赖：无（纯 lexer 层，零外部依赖）。

## 关联条目

- 原 `docs/known_limitations.md`（Architecture boundaries → lexer raw-capture）
- yaml 语言包（`grammar/yaml/`，块标量消费方）
