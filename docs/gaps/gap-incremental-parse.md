# Gap — 增量解析（块 7 · P1 解析层最小前置）

- 状态：**P1 已实现（2026-10-31，verified）**；跨文件语义失效传播（P3.4）与常驻 watch 明确属 v0.2 核心
- 关联：`ROADMAP.md` P3.2（失效判定 + 增量重解析）/ P3.4（增量 check）；`PROGRESS.md` 块 7
- 参照：`docs/references.md` 增量方向；`gap-verification-engineering.md` 条目 5（无增量解析，已跟踪）
  Doc: docs/gaps/README.md

## 缺口与范围决策

`PROGRESS.md` 块 7 的判据是"单函数编辑重解析 ≥5x / 增量诊断 = 全量结果 / 编辑器接口"；
但 `ROADMAP.md` P3（含 P3.2/P3.4）明确标注 **v0.2 核心、非收尾**。故 0.1.4 内只做**最小前置**：

- **做**：单文件、单顶层单元被编辑时，只重解析该单元的 token 子集并替换 AST 子节点；
  判不准即**保守回退全量**；提供库级"编辑器接口"（一次编辑 → 新 AST + 重解析统计）。
- **不做**：跨文件语义失效传播、规则失效键、信号图增量、常驻服务 + watch、缓存持久化
  ——全部留 P3.4（v0.2），触发条件见本文末。

**边界理由**：解析层是唯一可独立验证"≥5x"的一层；语义层增量在 0.1.4 没有可靠判据
（跨文件规则 W104/W105 的失效正确性需信号图增量先验证，见 ROADMAP P3.4 前置）。

## 现状底座（可复用）

- **span 已绑**（P3.1）：`Node._tok_span = (start_idx, end_idx)`（`parser/_production.py` 在规则匹配入口登记）。
- **Parser 可对任意 token 子集工作**：`Parser.parse(tokens)` 每次重置状态；`ParseContext` 支持快照/回退。
- **块解析器可直接复用**：`parser/block_parser.py` 的 `parse_block_body` / `parse_sentence`（本 P1 走 `parse` 子集，不碰这两者）。
- **AST 可变**：`Node.CHILDREN_FIELD`（`sub_node`）是普通 list；替换子节点 = 列表赋值。
- **符号门控要绕开**：C 声明 `[parser] symbol_namespaces`（typedef 消歧）⇒ 跨单元解析需要作用域重放；
  P1 **检测到 `parser.symbol_namespaces` 非空即回退全量**（V 未声明 ⇒ 空表，可增量）。

## 方案（P1）

1. **token 级 diff**：按 `(type, content)` 求公共前缀/后缀，得 `[pfx, old_end)` 与 `[pfx, new_end)`
   两个变更区间；完全相同 → 直接复用旧 AST（0 重解析）。
2. **定位顶层单元**：用旧 AST 顶层子节点的 `_tok_span`，找**完整覆盖旧变更区间**的最小单元；
   找不到（改动跨多单元/尾部注释区/span 缺失）→ 回退全量。
3. **只重解析该单元**：`parser.parse(new_tokens[s:e])`（s 不变，e 按 edit delta 平移），
   要求恰好得到 1 个顶层子节点，否则回退。
4. **并树**：把新子节点替换旧 AST 顶层 children 的对应项；`_tok_span` 平移到绝对新下标
   （`(new_s, new_s + len(sub))`）；其余子节点与其 span 不动（P1 每次编辑重建一次，不做多编辑累积修正）。
5. **接口**：`incremental_reparse(parser, old_tokens, new_tokens, old_ast) -> ReparseResult`
   （`ast / tokens_total / tokens_reparsed / fallback`）；文件级封装（读源/词法/编辑 API）留给
   P2 编辑器接入，不在本 P1 承诺。

## 判据草案

1. **≥5x（解析层）**：tv80（165KB）改一个函数内常量 → 全量 parse vs 增量 parse wall 比
   **≥5x**（`tests/engine/parser/test_incremental.py` 记录 PRE/POST 数字；本机复跑脚本）。
2. **增量结果 = 全量结果**：增量 AST 与"同一新源全量 parse"的 AST 结构逐节点相等
   （node_name / content / 子节点序；注释锚属性不计）；等价于诊断相等（分析是 AST + 配置的纯函数）。
3. **保守回退**：改动跨多单元 / 首尾（prefix=0 或 suffix=0）/ 符号门控语言 → `fallback != ""`
   且结果等于全量（回退 ≠ 错误）。
4. **无变更复用**：新旧 token 相同 → `tokens_reparsed == 0` 且返回同一 AST 对象。
5. **回归守卫**：既有 parser/analyzer/verilog 测试不变；A/B 0/144（管线侧未改，作护栏）。

## 预算与止损

- **预算**：≤2 生产文件（`parser/incremental.py` + 必要时 parser 导出口）+ ≤1 测试文件；
  调研探针上限 20（已用 ~12）。
- **止损点（预声明）**：若 `_tok_span` 在真实语料上不能稳定覆盖顶层单元（或 `parse(子集)` 对
  非 TranslationUnit 起始 token 不成立），则 P1 只交付 **diff + 回退 + 统计** 的接口与判据 2–4，
  判据 1 标 `partial`，并把"span 补齐"落 P3.2；**块 7 不标 ✅**。

## 不做 / 否掉

| 不做 | 反证 | 触发条件 |
|---|---|---|
| 跨文件语义失效传播（P3.4） | 0.1.4 无可靠判据；需信号图增量先验证 | v0.2 P3.4 立项 |
| 常驻服务 + watch（编辑器部署形态） | 需 LSP 分发形态，超出 0.1.4 边界 | 有真实编辑器集成需求 |
| 解析期符号门控语言的增量（C typedef） | 跨单元解析需作用域重放，P1 无 span 保障 | P3.2 作用域快照方案落地 |
| 多编辑累积修正（一次会话多次编辑） | 每次编辑走一次 `incremental_reparse` 即可；累积修正收益未验证 | 有编辑器复用实测数据 |

## 实现记录（P1，2026-10-31）

- 落点：`parser/incremental.py::incremental_reparse` + `tests/engine/parser/test_incremental.py`（5 测试）。
- **判据结果**：
  1. ≥5x：tv80（展开后 170,327 字符 / 22,604 tokens / 127 顶层单元）改一个标识符 →
     全量 parse **1.508s** vs 增量 **0.062s** = **24.3x**（`test_real_corpus_speedup_at_least_5x`）。
  2. 增量结果 = 全量：增量 AST 与全量 parse 的指纹（node_name/content/子节点序）逐节点相等
     （`test_single_unit_edit_matches_full_parse` / 真实语料用例）。
  3. 保守回退：多单元改动 → `full:unit-not-found`；C（`parser.symbol_namespaces` 非空）→
     `full:symbol-gate`；回退结果均等于全量。
  4. 无变更复用：`tokens_reparsed == 0` 且返回同一 AST 对象。
- 复跑：`python -m pytest tests/engine/parser/test_incremental.py -q`；
  `python -m pytest tests/engine/parser -q`（221 passed）；`tests/e2e/eval_lint_accuracy.py`。
- 偏差：真实语料必须先走宏展开（tv80 原文含 `` `define ``，直接 parse 会在 token 49 截断）；
  测试内用 `scan_directives` + `expand_tokens` 复现 check 同路。
- 回退保守面的实测边界：增量只对"完整落在某顶层单元 span 内"的改动生效；注释/空白区改动、
  跨单元改动、符号门控语言均走全量（漏失效 = 漏报，宁可慢不可错）。

## 实现记录（P2 片段级，2026-10-31）

- 思路（作者提出）：**片段模式本身就是增量解析的前置**——岛 = 语法配置推导的片段；拿变更
  片段的上下界喂片段解析得到片段树，并回父节点即增量解析。
- 落点：
  - `parser/parser_core.py::Parser.parse_fragment(tokens, rule_name)`——按**规则名**解析
    token 子集（规则名来自 AST 节点名 = 配置派生，零语言知识）；要求恰好吃完（尾随 trivia 除外）。
  - `parser/incremental.py` 三级：**片段级**（最深覆盖变更的 span 节点 → `parse_fragment`）
    → **单元级**（顶层单元整段 `parse`，P1）→ **全量**；`ReparseResult.level` 记录实际层级。
- 判据结果（tv80，22,604 tokens / 127 顶层单元）：
  | 编辑 | level | 重解析 tokens | 全量 parse | 增量 | 加速 | AST=全量 |
  |---|---|---|---|---|---|---|
  | 模块级（改 `clk`） | fragment（ModuleDecl） | 733 | 1386ms | 61.4ms | 23x | ✓ |
  | 语句级（`1'b0`→`1'b1`） | **fragment（AlwaysStmt）** | **329** | 1540ms | **22.9ms** | **67x** | ✓ |
- 注释边界：初版"含注释即回退单元级"，实测 tv80 采样 5/5 编辑在含注释片段上与全量逐节点
  等价 → 去掉该闸门（含注释也走片段级）；注释锚跨片段边界仍**无形式保证**，由
  `test_comment_inside_region_fragment_equals_full` + 真实语料等价用例盯住，出现不等价即回退。
- 测试：`tests/engine/parser/test_incremental.py` 8 测试（无变更复用、单/多单元、C 符号门控
  回退、片段级、注释片段、tv80 模块级 ≥5x、tv80 语句级 <400 tokens、多单元回退=全量）。
- 复跑：`python -m pytest tests/engine/parser/test_incremental.py -q`；`python -m pytest tests/engine/parser -q`。
