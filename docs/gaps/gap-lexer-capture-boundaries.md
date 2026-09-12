# Gap — lexer 捕获边界（块标量折叠 / 触发条件）

- 状态：部分闭环——原 item1「定界符限单字符」**已闭环（2026-09-12）**；
  剩余 2 项未立项
- 关联：原 `docs/known_limitations.md` Architecture 边界（2026-09-04 按部件拆入本档）
- 参照：YAML 块标量（`|`/`>`）语义

## 缺口是什么

`lexer/capture_runner.py`（CaptureRunner 原语）捕获原文直到行尾/字面标记/
整行匹配/闭合定界符/列比较（`indent_leq`——YAML 块标量 `|`/`>` 在内容缩进
≤ 触发行时终止）。注释/字符串/heredoc/fenced 块/块标量均配置声明
（`[comment] pairs`、`[string] delimiters`、`[[capture]]` 含可选
`after`/`next_chars` 触发）。**两个剩余缺口**（原第 3 项「多字符定界符」
已闭环，见下）：

1. **块标量内容原样捕获**：折叠（`>`）、chomping（`-`/`+`）、缩进指示符被
   保留但不做语义展开；指示符行注释随 token 一起带走。
2. **触发条件限声明式二元组**：prev-token-in-set + next-char-in-set 对，
   更丰富的上下文谓词需另一机制。

### 已闭环：多字符定界符（2026-09-12）

原缺口：`marker`/`line_match` 类已用 `text[pos:pos+end_len]` 支持多字符 `end`，
**唯 `delim` 类**的终止判定是 `ch == rule.end`（单字符比较）——配 `"""` 会
**静默**永不终止（退化为"到行尾"，把后续 token 一起吞进字符串）。

修法（按长度比较，与 `marker`/`line_match` 统一）+ 实测：

- `delimiters = ['"""']` 同起同止多字符 ✓；`[[capture]] kind="delim"` 配
  `start='r#"'` / `end='"#'` 的**起止不同**形态 ✓（`CaptureRule` 本就支持
  二者不同，无需扩类）。
- 顺带删除 `lexer/main_lexer.py` 中**不可达**的"字符串分支" + `_string_delims`
  （A1 死码）：清空该集合后 verilog/c4/yaml 三包的字符串 token 完全不变。
- 回归：`tests/engine/lexer/test_capture_runner.py`（+4 用例）。

## 为什么是缺口（影响面）

yaml 语言包（块标量）受影响；折叠/chomping 不语义化让 yaml 往返保真依赖
"保留原样"而非"正确语义重排"。

## 成熟解法参照（见贤思齐）

- YAML 规范对 `>` 折叠与 `-`/`+` chomping 有精确语义——直接借鉴其折叠规则。

## 可实现性

- 折叠/chomping：捕获后按 YAML 语义后处理（折叠空格/保留尾行）。
- 触发谓词：capture 触发条件从声明式对扩展为（保留声明式兜底）低优先级。
- 验证：yaml/c4 语言包测试 + 往返保真门禁。
- 当前依赖：无（纯 lexer 层，零外部依赖）。

## 关联条目

- 原 `docs/known_limitations.md`（Architecture boundaries → lexer raw-capture）
- yaml 语言包（`grammar/yaml/`，块标量消费方）
- 已闭环项回归：`tests/engine/lexer/test_capture_runner.py`（多字符定界符 +
  最长 start）；`lexer/capture_runner.py::run` delim 分支
