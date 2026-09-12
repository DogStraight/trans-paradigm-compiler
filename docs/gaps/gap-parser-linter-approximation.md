# Gap — parser/linter 错误处理近似（无解析器恢复 + 启发式边界）

- 状态：接受（设计选择，标注源码；非待闭环）——2026-09-13 复核：**不变**。
  唯一的例外情形（宏落在语法位）**不靠恢复解决**：按
  `docs/decisions/0017-macro-in-syntax-position.md`，parser 直产宏节点、
  句级检查前移到 linter 展开路径——"跳过能力已在 linter"，不必在 parser 重建。
- 关联：原 `docs/known_limitations.md` Architecture/Correctness 边界
  （2026-09-04 按部件拆入本档）；`linter/linter_architecture.md`（已知边界表）；
  `docs/decisions/0017-macro-in-syntax-position.md`（宏位路径）
- 参照：yacc/antlr 的错误恢复（skip-to-sync）、svlint/verible 对坏输入的容错

## 边界是什么

**parser 无错误恢复**：经典递归下降 + Pratt（LL 风格）——非 LR/GLR，且无
解析器级错误恢复（无 skip-to-sync-and-continue）。语法错误由**前置 linter**
拦截并阻断管线；若畸形输入漏过 linter，parser truncation **也阻断管线**
（2026-08-22 fuzz 发现：截断解析曾渲染部分输出并报 `success=True`——静默
内容丢失，已修）。

> **2026-09-13 复核（宏语法位）**：本条的"无恢复"**不变**。宏落在语法位时
> （实测一个端口类型位为展开锚 → 整棵树 0 节点）**不用恢复去解决**——按
> ADR-0017：parser 直产宏节点（宏位可解析为节点）、句级检查前移到 linter 展开
> 路径（跳过能力本就在 linter）。故"真语法错 = linter 前置 + truncation 双保险"
> 这条分工保持原样。

**linter 启发式不可避免**：前置 linter 工作在坏代码上，错误恢复是对开放
坏输入集的有限近似。少数兜底（语句结束 = 分号/行尾、容器结束 = 派生
`_stmt_ends`、单 token 规则形态）是显式"语言约定近似"，不能完全从语法
推导——已在源码标注。

> **2026-09-13 新实测边界（多行 RHS 内注释）**：展开路径的宏体若被**文本铺入**
> 且自带行尾注释，发现器会级联失守（darkriscv：81 条 `phase-unrecognized`，
> 同一文件改为 token 级锚窗口拼接后 0 条）；进一步定位：即使避开注释吞没，
> **多行 RHS 表达式中间出现注释 token** 仍会让发现器认不出该语句
> （同一文件实测 26 条，去掉体注释即 0）。故锚窗口拼接只带展开体的语法 token
> （体注释不进窗口）——这是绕开该边界，不是修好它；边界本身仍开放。

## 为什么接受（影响面）

- 语法错误由 linter 单点拦截 + truncation 双保险阻断，"无恢复"不会静默产出
  坏输出；恢复功能（skip-to-sync）收益低、实现贵，且会与 linter 职责重叠。
- linter 启发式覆盖的是"坏输入"这个开放集，有限近似不可避免——精确性靠
  e2e lint 语料门禁（recall 31/31 零误报基线）锁住。

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

- `linter/linter_architecture.md`「已知边界问题」表（多行 RHS / `@*` 敏感列表
  等，TODO 后置）
- 原 `docs/known_limitations.md`（Correctness linter heuristics / Architecture
  parser no recovery）
- lint recall 门禁：`tests/e2e/eval_lint_accuracy.py`
