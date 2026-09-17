# Gap — 预处理器注释扫描（行级近似）

- 状态：接受（近似面窄，实测零命中，闭环代价大于收益）
- 关联：`preprocessor/_expand.py::scan_directives`；`docs/gaps/gap-lexer-capture-boundaries.md`

## 边界是什么

`scan_directives` 判定"某行是不是指令行"时，用**行级状态机**（`_advance_block_comment`）
推注释跨度：标记来自语言包声明（`kind = marker` 的跨行定界符对 + `kind = line` 的
行注释起始标记），注释内部的行不作指令识别，行注释文本跳过。这套跨度判定**与词法
捕获器（`lexer/capture_runner.py`）不同源**——捕获器兼顾字符串，行级状态机不看。
由此两处近似：

1. **字符串内的定界符形态被当作注释标记**：`$display("/*")` 会让后续行进"注释内部"
   状态直到出现 `*/`，期间的指令不被识别（`$display("//")` 触发的是"跳过本行余下"，
   无跨行后果）。
2. **注释之后的同行指令不识别**：`/* c */ \`define W 1` 的行首是注释而非指令前缀 →
   该行原样保留、`define` 不展开（修复前同样不识别，非回归）。

为什么接受：138 份真实样本实测两处均 **0 例**（字符串含定界符 0、同行块注释后紧跟
指令 0）；两者都要求"注释跨度与字符串跨度共存"，与捕获器同源才是正解，而现有行级
状态机恰是为此前的两起真实事故（注释内伪指令、行注释含 `/*`）落地的最窄改动面。

## 可实现性（若闭环）

- 范围：`_advance_block_comment` 改为"向词法捕获器要注释/字符串跨度"，行级状态从
  捕获结果推，不再自带一套标记扫描。
- 依赖：行内偏移 → 指令行首的换算（现有 `clean_to_raw` 行账本已具备行映射）。
- 验证：`tests/engine/preprocessor/test_directive_in_comment.py` 中锁住两条近似的断言
  改为期望正确行为；真实语料诊断基线（`tests/e2e/eval_diag_baseline.py`）不涨。

## 关联条目

- 门禁：`tests/engine/preprocessor/test_directive_in_comment.py`（近似锁在断言里）
- 机制：`docs/pipeline_stages.md`（预处理器阶段）、
  `docs/gaps/gap-lexer-capture-boundaries.md`（捕获器侧边界）
