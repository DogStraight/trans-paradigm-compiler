# Gap — parser/linter 错误处理近似（无解析器恢复 + 启发式边界）

- 状态：接受（设计选择，标注源码；非待闭环）。宏落语法位的情形不走 parser
  恢复：宏边界节点由管线就树产生、句级检查前移 linter 展开路径（跳过能力本
  就在 linter，不必在 parser 重建）。
- 关联：`linter/linter_architecture.md`（已知边界表）
- 参照：yacc/antlr 的错误恢复（skip-to-sync）、svlint/verible 对坏输入的容错

## 边界是什么

**parser 无错误恢复**：经典递归下降 + Pratt（LL 风格）——非 LR/GLR，且无
解析器级错误恢复（无 skip-to-sync-and-continue）。语法错误由**前置 linter**
拦截并阻断管线；若畸形输入漏过 linter，parser truncation **也阻断管线**
（2026-08-22 fuzz 发现：截断解析曾渲染部分输出并报 `success=True`——静默
内容丢失，已修）。

**linter 启发式不可避免**：前置 linter 工作在坏代码上，错误恢复是对开放
坏输入集的有限近似。少数兜底（语句结束 = 派生 `_stmt_ends` ∪ 行尾
newline 惯例；容器结束 = 匹配失败回退派生 `_stmt_ends`）是显式标注的"语言约定近似"，不能完全从语法
推导——已在源码标注。

## 为什么接受（影响面）

- 语法错误由 linter 单点拦截 + truncation 双保险阻断，"无恢复"不会静默产出
  坏输出；恢复功能（skip-to-sync）收益低、实现贵，且会与 linter 职责重叠。
- linter 启发式覆盖的是"坏输入"这个开放集，有限近似不可避免——精确性靠
  e2e lint 语料门禁（错误样本 33/33 全检出、合法样本 0 误报——
  `eval_lint_accuracy` 实测）锁住。

## 成熟解法参照（见贤思齐）

- yacc/antlr 的 panic-mode/skip-to-sync 错误恢复——若要"一个语法错误后继续
  报更多错"，是参照方向；tpc 走"linter 前置单点 + 阻断"路线，职责已分给
  linter，parser 保持纯。
- svlint/verible 对坏输入的诊断形态（`file:line:col: msg`）——linter 输出
  对齐参照，见 `tests/e2e/eval_lint_accuracy.py`。

## 可实现性（若要改）

- parser 级恢复：需在 production 匹配失败处引入同步点集合（end_case/块结束），
  属引擎改动、收益有限——**当前无计划，接受现状**。
- linter 近似面收窄：随语法规则完善（`_stmt_ends` 推导）自动收窄，非独立任务。

## 关联条目

- `linter/linter_architecture.md`「已知边界问题」表（多行 RHS / `@*` 敏感列表等）
- lint recall 门禁：`tests/e2e/eval_lint_accuracy.py`


## C 语言包暴露的语句发现缺口（2026-09-25 实测）

`grammar/c/` 的**解析侧完全正常**（整文件进 AST、结构与计数都可查），但同一份合法
声明序列过 linter 会报 **17 条** `phase-statement` / `phase-unrecognized`。
样本：`tests/languages/c/samples/ring_buffer.h`（真实风格头文件），逐条分布见
`tests/languages/c/test_c_corpus.py::test_linter_gap_is_recorded_not_hidden`。

**四类构造函数**（linter 的语句发现与"语句结束"判定跟不上）：

| 构造 | 报文 | 例 |
|---|---|---|
| 带成员体的类型说明符 | `expected ';', got '{'` | `struct ring_item { … };` / `union ring_slot { … };` / `enum … { … };` |
| 成员声明里的数组后缀 | `expected ';', got '['` | `struct ring_item items[16];` |
| 带括号的声明符 | `unexpected '('` | `int ring_push(struct ring *r, …);` |
| 枚举体内的 `=` | `unrecognized statement` | `enum { RING_FULL = 2 };` |

**为什么值得修**：C 的声明形态（体、声明符括号、成员后缀）与 verilog/c4 的差异大，
现有近似（首 token 挑语句 + 启发式找语句结束）在 C 上**误报率 100%**（合法代码全报），
这会让 C 包的检查链在最基础的头文件上不可用。

### 归因（2026-09-25，已定位到代码，两个**不同**机制）

**机制 A —— 严格逐 token 匹配不回溯**（覆盖 `{` / `[` / `(` 三类，共 15 条）：

- 报文出处：`linter/checkers/matcher.py::_match_token`（`expected '<tok>', got '<actual>'`）。
- 证据链（`struct ring_item { … };`）：`Declaration` 产生式逐元素走 —
  ① `@StorageClass|@TypeQualifier|@TypeSpecifier` 吃掉 `struct ring_item`（说明符交替可用）；
  ② `@SpecRest*` 匹配 0 次；③ `@DeclaratorList?` 匹配 0 次（下一 token 是 `{`，起不了声明符）；
  ④ 期望 `symbol.base.semicolon`，实得 `bracket.l_curly_bracket` → 报错。
- 结论：**规则内部的可选分支（`StructSpecifier` 的 `@StructBody?`）没有被尝试**——
  匹配器在"后续必需元素失败"时不会回头去取前面可选元素的分支（无回溯）。
  `[`（`(@ArraySuffix|@FuncSuffix)*` 组量词）与 `(`（同一组的 `@FuncSuffix`）同因。

**机制 B —— 首 token 候选缺路径**（覆盖 `enum` 类，2 条）：

- 报文出处：`linter/discovery.py::_record_unrecognized`（`unrecognized statement:
  no grammar rule matches here`），触发条件 = `lookahead.classify()` 返回**空候选**。
- 现象：`enum` 开头的行完全没有候选，而 `struct` 开头的行有候选（`Declaration`）。
- 结论：首 token 映射的推导在 `enum` 这条路径上断了（`keyword.enum` 经
  `EnumSpecifier`/`AnonEnumSpecifier` → `TypeSpecifier` 的交替），需要查推导为何
  只覆盖到 `struct` 那一支。

### 修点与判据（按归因分两条，各自可独立验证）

1. **机制 A**：`matcher` 对 `?` / `*` / 组的处理要能在"后续必需元素失败"时**回溯取
   可选分支**（或至少对 `?` 做"先试可选、失败再跳过"的正确语义）。判据：C 语料样本上
   `phase-statement` 类报文归零，且 verilog/c4/yaml 三包既有 lint 测试与真实语料
   误报基线**不退化**（这是引擎侧改动，影响面必须用三包 + 基线锁住）。
2. **机制 B**：`lookahead` 的首 token 推导对"规则内交替"要一致覆盖（`enum` 与 `struct`
   同源却只覆盖一支）。判据：`enum` 开头的行有候选；`unrecognized` 类报文归零。
3. **包侧兜底（不推荐先做）**：把 `StructSpecifier` 的 `@StructBody?` 拆成两条规则交替
   （带体 / 不带体）可绕开机制 A——但那是在语言包里迁就匹配器的缺陷，且改变 AST 形状；
   仅当引擎侧改动风险过高时作为临时方案，并须写明"待引擎修复后回退"。

⚠ 回归守：`tests/languages/c/test_c_corpus.py::test_linter_gap_is_recorded_not_hidden`
断言的是"诊断全落在两类已知码 + 数量 = 17"——**修好后该用例会失败**，届时按上面的
判据换成"无诊断"并复核本档。
