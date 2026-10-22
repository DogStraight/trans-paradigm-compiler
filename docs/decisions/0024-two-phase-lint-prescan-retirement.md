# ADR-0024: 退役 lexer 预扫描 + 依赖它的 raw 管线（符号判定后移 analyze）

- Status: **active（T2 执行中）**；作者 2026-10-22 定调"待刻度完成后作专项整治"，
  2026-10-23 主线 1 刻度 9/9 完成 → 取回执行。
- 历史：2026-10-22 #45 调查出两阶段设计；#49 删除 parser 侧预扫描消费面
  （`pre_symbols`/`pre_hints`/`rule_hints`，零消费、A/B 0/144）。
- 关联：`docs/gaps/gap-c-semantic-base.md`（预扫描期）、`gap-parser-linter-approximation.md`
  （M1 资格/raw 承载）、`linter/linter_architecture.md`、`docs/decisions/0021-*`（延期策略）

## 背景

`pre_scan` 是 lexer 之后、parser 之前的**文本级正则扫描**（`lexer/pre_scan.py`，产出
`{name: kind}` + 行/列/深度；平坦、首见归属、无声明顺序，模块自述"不是精确的"）。
作者判断："lexer 层选出的符号信息量严重不足，宁可延后到分析阶段"。

原设计（#45）只能把符号判定后移到 analyze：linter M1 保留**符号无关双读试解析**，
raw 承载到 parse、analyze 用精确符号表裁决（E002/E003）。**#49 G4 改变了前提**：
parser 已内建符号表 + `CastTypedefName` 门控，typedef 强转在**解析期**直接建树
（正确 AST，不再需要 raw 兜底）；T1（#51/#52）又清掉预处理器时序与语料门禁。
⇒ 原先"唯一承重面 = linter raw 资格"的结论需要复裁。

## #53 复裁（2026-10-23）：pre_scan 已零承重

**实验**（临时注释两包 `tpc.toml` 的 `[lexer] pre_scan` 声明，其余不动，测后还原）：

| 面 | pre_scan 禁用后 |
|---|---|
| `tests/languages/c` + `tests/engine/linter` + `tests/engine/pipeline` | **1617 passed / 1 failed**（唯一失败 = 断言"存在 pre_scan 期记录"的死测试 `test_phases_are_distinguishable`） |
| C 真实语料 7 文件（`real_c_ref`） | **全部 parse_ok、0 诊断**（与启用一致） |
| typedef 强转 / 指针强转 / 复合字面量 | 前两者 #49 直接解析；复合字面量由 **T2a**（本 ADR 切片）补齐后直接解析 |

**结论**：G4（#49）+ T2a 后，`pre_scan` 的**唯一历史承重面（raw 资格）已无消费者**；
连带地，**raw 管线本身（P3c 位点发现 / M2 摘诊断 / raw 承载 / P4 理解提升 /
E002·E003 安全网）在 C 上也不再被生产路径使用**（raw 位点只能来自 M1 资格，而 M1 的
符号来源即 pre_scan；无 pre_scan ⇒ eligible 恒 false）。⇒ T2 = **删除两条已死机制**，
不是"两阶段改造"。

## 决策与切片

- **T2a（✅ 本提交）**：C `CompoundLiteral` 类型名收 `@CastTypeName|@CastTypedefName`
  （复用 #49 门控）⇒ `(t){1}` 直接建树；P4 的"复合字面量 raw 边界"测试改为直接结构断言；
  变异：去该分支 ⇒ 用例红（清单 123 条）。
- **T2b（下一轮，删除 pre_scan 本体）**：
  - 引擎：`lexer/pre_scan.py` 整文件、`lexer/__init__` 导出、`core/global_state.py` 的
    `lexer.pre_scan._CACHE`、`core/engine_capabilities.py` 能力族串、`analyzer/structure.py`
    的预扫描读取（若有）、两包 `tpc.toml` 的 `[lexer] pre_scan` 行、`grammar/{c,verilog}/
    base/_pre_scan.toml`；
  - linter：`scanner.py` 的 `_pre_scan_symbols`/`load_pre_scan_config`/`set_symbol_hints`
    （M1② kind/name 过滤、③ 声明先后/深度、`raw_exclude_rules` 读取）与 `lookahead.py`
    对应字段 —— **M1 位点发现整体失去意义 ⇒ 与 T2c 一起删**；若拆轮，先让 M1 静态化
    （`eligible` 恒 false）并在 T2c 删除；
  - C 包：`grammar/c/plugins/semantics/_api.py` 的 `two_phase_product`/`pre_scan_records`/
    `merge_phases`/`phases_for`/`PHASE_PRE_SCAN`（管线无消费者，仅测试/文档引用）；
  - 测试/文档：删 `test_pre_scan_fallback.py`、`test_c_symbol_collection.py` 分期用例、
    linter 符号提示/资格测试（67 条已 skip 的 raw 资格面随 T2c 一并处置）、
    `docs/gaps/gap-c-semantic-base.md` 预扫描期条目、两包 README、`MODEL_INDEX.md`、
    变更日志/变异表同步。
- **T2c（删除 raw 管线，需先证后删）**：`linter/lookahead.py` M1 资格证据（`_type_name_hits`/
  `_substitution_trial`/收敛 warning 面）、`scanner._apply_narrow_downgrade`、`parser` raw
  承载（`raw_sites`/`raw_source`/`try_raw_sentence`/`build_raw_candidate`）、
  `grammar/c/plugins/semantics/_raw_understand.py`/`_raw_transform.py`、
  `analyzer/primitives/_raw_validate.py`（E002）与 E003、相关测试（含 67 skip）。
  **删除判据**：`grep` 生产路径无消费者（T2b 后 raw_sites 恒空）+ 全量/A-B/c_acceptance/
  真实语料门禁不变 + 变异表删除对应条。
- **T2d（文档收口）**：机制文档（linter/parser README）与 gap 档改写；`pre_scan` 全仓 grep
  归零（docs 历史说明除外）；本 ADR 删除。

## 权衡

**得到**：删两条死机制（预扫描 + raw 管线）、一个引擎阶段旋钮、两包配置与四处测试面；
符号判定单一真相 = parser `_ScopeStack` + analyze 精确作用域；`tpc lint` 不再做文本级符号猜测。

**付出/风险**：① lint/check 分工变化（候选 raw 面不再存在）需 README/CHANGELOG 明示；
② raw 删除是大删除（回滚 = revert 单提交）；③ `.agents` 外测试文档需同步，防"删了机制留下
幽灵引用"；④ 变异表需删/改 raw 相关条目，保持门禁有效。

## 验证（逐片）

- **T2b**：`tests/languages/c`、`tests/engine/linter|pipeline`、`tests/e2e`、`tests/policy`
  全绿（除显式删除的测试）；`grep -r "pre_scan" lexer parser linter analyzer pipeline
  grammar` = 0（docs 除外）；`python tools/ab_pipeline_compare.py --mode cli --products`
  **0/144**；真实语料门禁 `test_diag_baseline_c` 仍 0 诊断；pyright 0。
- **T2c**：全量 `pytest tests` 绿；`c_acceptance` 49/0；A/B 0/144；render_coverage 100%；
  真实语料门禁不变；变异表同步；raw 相关 skip 清零（删/改写完成）。
- **止损**：若 T2c 发现任一生产路径仍依赖 raw（如某语法形态只在 raw 下可解析）⇒ 保留该最小
  面并登记"只此一形态"边界，其余删除；不得为删机制接受解析/诊断回归。

## 不做 / 想过的备选

- **保留最小 pre_scan（只服务 linter）**：作者否（lexer 层信息量不足；单一真相冲突）。
- **两阶段保留 raw、只做符号无关化**：G4 后 raw 无生产消费者；为"将来可能用"保留死机制
  违反删除纪律；否。
- **linter 直接读 analyzer 表**：管线顺序不允许（analyze 在 parse 之后）；否。
- **全删且接受 C raw 能力回退**：9+33 测试回退、真实 C 语料误报增长（大量 typedef 强转/
  复合字面量）；T2a/G4 已使该代价消失，否。

## Impl 现状（#53）

`linter/lookahead.py::_record_convergence`（M1①–④）、`linter/scanner.py::_apply_narrow_downgrade`
（M2）、`parser/block_parser.py::build_raw_candidate`（raw 承载）、
`analyzer/primitives/_raw_validate.py::validate_raw_statement`（E002）、
`grammar/c/plugins/semantics/_raw_understand.py`（E003）/`_raw_transform.py`（提升）；
测试面：`tests/engine/linter/test_linter_raw_eligibility.py`、`test_linter_symbol_hints.py`、
`tests/engine/pipeline/test_lint_internal_warnings.py`、`tests/engine/parser/test_parser_raw_site.py`、
`tests/languages/c/test_c_raw_understanding.py`、`tests/e2e/eval_lint_accuracy.py`。
