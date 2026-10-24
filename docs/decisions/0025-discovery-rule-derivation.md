# ADR-0025: 语句发现改为「声明式形态推导」，消除 C 形态特例补丁

- Status: draft（未立项设计输入；立项实现后升 accepted）
- Date: 2026-10-30

## 背景

`linter/discovery.py`（816 行）负责"把 token 流切成语句区间并递归成树"，供
`StatementChecker` 逐句做精确诊断。它在**没有解析器**的前提下工作（坏输入也要能定位），
因此不能直接用 parser 的 production 求值——这是它存在的正当理由（见
`docs/gaps/gap-parser-linter-approximation.md`：parser 无错误恢复，linter 必须自己切边界）。

问题不在"有第二套匹配"，而在**这套匹配的形状判定靠特例累积**。实证（git log 逐条溯源）：

| 补丁 | 提交 | 针对的语言形态 |
|---|---|---|
| `_advance_match` 零进展 `j+1` 兜底 | afd83f0 | C 函数体 `{...}` body 起点错位 |
| 括号分支转块分支 | afd83f0 | C `CompoundStmt = { @Stmt* }` 静默漏检 |
| `_is_bracket_stmt_container` | afd83f0 / 26a7df2 | 同上，且要排除 `[[attr]] int f(){...}` |
| `_stmt_recovery_depth` + `fallback_statement_names` | 26a7df2 | 容器 body 内试解析失败要逐条报 |
| `scanner._is_pure_stmt_container` | 26a7df2 | 同上（父检查器让位） |
| `_block_body` 起点重算 / `_stmt_tail_end` 尾部补算 | 26a7df2 | 块头 production 匹配收尾 |

即：**一个 C 语言形态（花括号语句容器）引发了 6+ 处点状补丁**。特征：
- `_is_bracket_stmt_container`（discovery）与 `_is_pure_stmt_container`（scanner）
  **近乎逐行重复**，只差"首元素是否为当前开括号"一项；
- `tools/structural_kept.json` 用**同一句理由**豁免了 5 个条目
  （`CLASS|discovery.py:Discovery`、`CLASS|lookahead.py:LookaheadTable`、
  `_is_bracket_stmt_container` 的 CC/COG、`_discover_statement` 的 CC/COG）——
  同一条理由登记 5 次，是"结构欠账未收敛"，不是"设计如此"。

**违反开闭原则的具体形态**：新增一个语言（或同一语言新增一种容器形态）时，
引擎侧必须**改 `discovery.py`**——`_derive_attr_openers` 硬编码了
`bracket.l_parentheses` + `symbol.base.multiple`（Verilog 属性对 `(* ... *)`），
`scanner.py:79` 硬编码了 `symbol.base.colon`。`policy/check_hardcode.py` 的 R1
只扫 grammar 词表关键字，**不覆盖 `bracket.*` / `symbol.*` 组合**——门禁盲区。

## 决策

**把"语法的形状"从引擎代码搬到语言声明面，引擎只留一条通用推导。**

沿用本项目已验证的既有模式（`analyzer/structure.py` + `grammar/<lang>/base/_structure.toml`：
"引擎不认语义、只按声明枚举与定位"）。新增**语句发现协议**声明段，引擎据声明推导：

```toml
# grammar/<lang>/base/_discovery.toml（草案）
[discovery]

# ① 语句容器：production 只含定界 token + 语句引用 —— 由**规则自身**声明，
#    引擎不再猜"像不像容器"
[discovery.containers]
# 规则名 = 容器体引用位（引擎据此递归 body 区间）
CompoundStmt = { body = "stmt_items" }      # C: { @Stmt* }
BeginEnd     = { body = "stmts" }           # Verilog: begin ... end（有 block_start/end）

# ② 属性/修饰前缀对：整体跳过、不注册语句节点（当前硬编码 (* ... *)）
[discovery.prefix_pairs]
# 形态 = [开 token, 次 token]（纯 token 名，与 production 同口径）
parallel_case = ["bracket.l_parentheses", "symbol.base.multiple"]

# ③ 容器结构延续关键字（else / default / impl …）—— 由规则显式列出，
#    引擎不再从"keyword 起始 + 非语句 + 引用语句"反推
[discovery.continuations]
keywords = ["keyword.else", "keyword.default"]
```

引擎侧收敛为**一个** `DiscoveryShape` 解析器（读声明 → 产出
`containers / prefix_pairs / continuations / openers / closers` 五张表），
`discovery.py` 只按表分派，不再含任何语言字面量。

### 为什么是"声明"而不是"更好的推导"

考虑过继续增强推导（当前 `_is_bracket_stmt_container` 已是从 production 结构推导，
`_derive_continuation_openers` 也从 production 推导）。**否决**：推导能猜出"这像容器"，
但猜不出**意图**——`[[nodiscard]] int f(void){...}` 与 `{...}` 在 production 结构上
同形（都是"定界 token + 语句引用"），区分它们的唯一依据是语义意图，只能声明。
继续加推导分支 = 继续加点状补丁，正是本 ADR 要消除的模式。

## 权衡

- 付出：语言包新增一个声明段（`verilog` / `c` / `c4` 各一份）；`discovery.py` 重构；
  `scanner._is_pure_stmt_container` 与 `_is_bracket_stmt_container` 合并为一份。
- 换回：新增语言/容器形态**不改引擎**（开闭原则）；两处重复判定合一；
  `structural_kept.json` 的 5 条同理由豁免可退场（可量化的收敛指标）；
  硬编码 `bracket.*`/`symbol.*` 消除。
- 被拒绝备选：
  - **保持现状 + 继续打补丁**：每加一种语言形态再补 2-3 处，欠账持续增长。
  - **用 parser 直接切边界**：parser 无错误恢复，坏输入场景失效——这正是 linter
    独立切边界的理由，且 `gap-parser-linter-approximation.md` 已把"无恢复"定为接受项。
  - **纯推导（不新增声明段）**：无法区分同形不同意图（见上）。

## 验证

- 行为零变化基线（硬要求）：`tests/engine/linter` + `tests/languages/c` + `tests/languages/c4`
  全绿；`eval_lint_accuracy.py` 保持 **33/33 召回、FP 0**；
  `eval_diag_baseline.py` **5548 条不增长**。
- 重构自证：`structural_kept.json` 中 5 条 discovery/lookahead 豁免退场，
  structural S 下降；`_is_bracket_stmt_container` / `_is_pure_stmt_container` 合并为一份
  （`CLONE` 项归零）。
- 开闭原则自证：新增一个测试用"假语言包"声明自己的容器与属性对，
  **不改任何引擎文件**即可通过发现（可用 `tools/min_pack_probe.py` 的既有机制）。
- 门禁补强：`policy/check_hardcode.py` 增设 **R6**——引擎字符串出现
  `bracket.*` / `symbol.*` 具体 token 名即报（当前 R1 盲区）。

> Impl: linter/discovery.py（`_derive_attr_openers` / `_is_bracket_stmt_container` /
> `_derive_continuation_openers`）· linter/scanner.py（`_is_pure_stmt_container`）
> （待立项新增声明段 `grammar/<lang>/base/_discovery.toml`——本 ADR 为未立项设计输入，
> 该文件尚不存在，故不作 Impl 锚）
> Test: tests/engine/linter/test_linter_discovery.py ·
> tests/languages/c/test_c_block_diagnostics.py · tests/languages/c4/test_c4_linter.py

## 分期（立项后）

| 期 | 内容 | 独立验证 |
|---|---|---|
| D1 | 新增声明段 + `DiscoveryShape` 解析器；**引擎行为不变**（声明值对齐当前推导结果） | 全量绿、S 不变 |
| D2 | `_derive_attr_openers` / `_derive_continuation_openers` 改读声明 | 同上 |
| D3 | 合并两处纯容器判定；`_is_bracket_stmt_container` 改读声明 | CLONE 项归零 |
| D4 | 补 R6 门禁；删过渡期推导代码 | 门禁不误报、S 下降 |
