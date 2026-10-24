# Gap — 注释/字符串跨度判定：两套实现与各自边界

- 状态：**部分接受 + 2 项未闭环**（见下：A 侧接受、B 侧未立项）
- 关联：`preprocessor/_expand.py::scan_directives`（B 侧）、`lexer/capture_runner.py::run`（A 侧）、
  `docs/pipeline_stages.md`（预处理器阶段）
- 参照：YAML 块标量（`|`/`>`）折叠与 chomping 语义（`docs/references.md`）

## 边界是什么

**同一事实（"这段文本里注释/字符串跨度到哪"）在引擎里有两套独立实现**，各自有边界：

### A 侧 — 词法捕获器（`lexer/capture_runner.py`）

捕获原文直到：行尾 / 字面标记 / 整行匹配 / 闭合定界符 / 列比较（`indent_leq`——YAML 块标量
`|`/`>` 在内容缩进 ≤ 触发行时终止）。注释 / 字符串 / heredoc / fenced 块 / 块标量均由语言包
声明（`[comment] pairs`、`[string] delimiters`、`[[capture]]` 含可选 `after`/`next_chars` 触发）。
**两项未闭环（未立项）**：

1. **块标量内容原样捕获**：折叠（`>`）、chomping（`-`/`+`）、缩进指示符被保留但不做语义展开；
   指示符行注释随 token 一起带走。
2. **触发条件限声明式二元组**：prev-token-in-set + next-char-in-set，更丰富的上下文谓词需另一机制。

影响面：yaml 语言包；折叠/chomping 不语义化 ⇒ yaml 往返保真依赖"保留原样"而非"正确语义重排"。
可实现性：捕获后按 YAML 语义后处理（折叠空格/保留尾行）；触发谓词先保留声明式兜底再扩展低优先级；
验证 = yaml/c4 包测试 + 往返保真门禁 + `tests/engine/lexer/test_capture_runner.py`。

### B 侧 — 预处理器行级状态机（`preprocessor/_expand.py`）

`scan_directives` 判定"某行是不是指令行"时**另有一套**行级状态机（`_advance_block_comment`）推
注释跨度：标记同样来自语言包声明（`kind = marker` 的跨行定界符对 + `kind = line` 的行注释起始），
但**不看字符串**。由此两处近似（**接受**：近似面窄、实测零命中、闭环代价大于收益）：

1. **字符串内的定界符形态被当作注释标记**：`$display("/*")` 会让后续行进"注释内部"状态直到 `*/`，
   期间的指令不被识别（`$display("//")` 只跳过本行余下，无跨行后果）。
2. **注释之后的同行指令不识别**：`/* c */ \`define W 1` 行首是注释而非指令前缀 ⇒ 该行原样保留、
   `define` 不展开（修复前同样不识别，非回归）。

为什么接受：两处都要求"注释跨度与字符串跨度共存"，**与 A 侧同源才是正解**；现有行级状态机是为此前
两起真实事故（注释内伪指令、行注释含 `/*`）落地的最窄改动面；历史语料实测两处均 0 例
（⚠ 该数字出自旧 CHANGELOG，**现仓内实语料 = `tests/e2e/samples/real/ref` 9 文件**，口径须重跑）。

## 为什么两档合一

A/B 是**同一根因的两面**：跨度判定没有单一来源。分别建档会让"要不要统一到捕获器"这个真正的
决策点被拆散在两处（B 侧的闭环方案恰好就是"向 A 侧要跨度"）。合一后单一来源记录：现状两套、
各自边界、以及统一的路径。

## 可实现性（B 侧闭环即收敛起点）

- 范围：`_advance_block_comment` 改为"向词法捕获器要注释/字符串跨度"，行级状态从捕获结果推，
  不再自带一套标记扫描。
- 依赖：行内偏移 → 指令行首的换算（现有 `clean_to_raw` 行账本已具备行映射）。
- 验证：`tests/engine/preprocessor/test_directive_in_comment.py` 中锁住两条近似的断言改为期望
  正确行为；真实语料诊断基线（`tests/e2e/eval_diag_baseline.py`）不涨。

## 关联条目

- 门禁：`tests/engine/preprocessor/test_directive_in_comment.py`（B 侧近似锁在断言里）、
  `tests/engine/lexer/test_capture_runner.py`（A 侧多字符定界符/最长 start 回归）
- 机制：`docs/pipeline_stages.md`（预处理器阶段）、`grammar/yaml/`（块标量消费方）
