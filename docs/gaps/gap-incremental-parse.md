# Gap — 增量解析（块 7 · P1 解析层最小前置）

- 状态：**P1 已实现（2026-10-31，verified）**；跨文件语义失效传播（P3.4）与常驻 watch 明确属 v0.2 核心
- 关联：`ROADMAP.md` P3 节（P3.2 已交付解析层最小面，残余见本文「不做」；P3.4 增量 check 未做）；`PROGRESS.md` 块 7
- 参照：`docs/references.md` 增量方向；`gap-verification-engineering.md` 条目 5（无增量解析，已跟踪）
  Doc: docs/gaps/README.md

## 缺口与范围决策

`PROGRESS.md` 块 7 的判据是"单函数编辑重解析 ≥5x / 增量诊断 = 全量结果 / 编辑器接口"；
但 `ROADMAP.md` P3（P3.2/P3.4 原定 v0.2 核心）标注 **非收尾**，而增量解析是**长期优化目标**。故 0.1.4 内只做**解析层最小面**：

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
  判据 1 标 `partial`，并把"span 补齐"落 P3.2 残余（本文「不做」表）；**块 7 不标 ✅**。

## 不做 / 否掉

| 不做 | 反证 | 触发条件 |
|---|---|---|
| 跨文件语义失效传播（P3.4） | 0.1.4 无可靠判据；需信号图增量先验证 | v0.2 P3.4 立项 |
| 常驻服务 + watch（编辑器部署形态） | 需 LSP 分发形态，超出 0.1.4 边界 | 有真实编辑器集成需求 |
| 解析期符号门控语言的增量（C typedef） | 跨单元解析需作用域重放，P1 无 span 保障 | P3.2 残余：作用域快照方案落地 |
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

## 诚实边界（增量解析是长期优化目标；本块只交付解析层最小面）

| 面 | 保证 | 不保证（长期目标） |
|---|---|---|
| 范围 | 单文件、单次编辑、同文件增量重解析；修改片 ≤ 20–30%（随规模放开）才走增量 | 跨文件语义失效/诊断增量（v0.2 P3.4）；常驻 watch/LSP 部署形态 |
| 正确性 | 覆盖的编辑子集上：增量 AST 与全量 parse **逐节点相等**（node_name/content/子节点序） | 任意编辑的形式化等价证明；注释锚跨片段边界无形式保证（实测 tv80 采样等价，靠等价测试盯住） |
| 粒度 | 最深**带 span** 节点（语句/块/单元）；片段级为主路径 | 叶子（标识符/字面量）无 `_tok_span` → 片段粒度止于最近祖先；补叶子 span 归 P3.2 残余 |
| 语言 | 无解析期符号门控的语言（V）可增量 | C（`[parser] symbol_namespaces` typedef 消歧）回退全量；其他门控语言同 |
| 生命周期 | 每次编辑独立重解析，不做累积修正 | 多编辑累积的 span 平移修正、持久化缓存、缓存失效判定（P3.2 残余） |
| 回退 | 判不准一律回退单元级/全量（回退结果=全量） | "回退即正确"依赖全量路径本身；全量路径的既有边界不因增量而改变 |

## 大改动阈值（经验次优，非固定值）

- 依据（作者 + 模型估算）：修改片超过文件 **~20–30%** 时，增量收益被摊薄、并树/一致性风险
  上升，不如直接全量重解析。**阈值不钉死**：小文件更保守（固定开销占比大），大文件放到 30%。
  注意：**这不是 tree-sitter 的实现事实**（其核心无改动占比阈值，见下节调研）——这是我们的
  产品级护栏，按"普遍次优"取舍。
- 实现：`_max_change_ratio(total) = 0.20 + 0.10 * min(1, total/20000)`（20k tokens 到顶 30%）。
  闸门 = 最细候选片段的 token 占比；超过 → `full:too-large` 回退全量（结果 = 全量）。
- 已知取舍：这是**启发式**（不是成本模型），按"普遍次优"设计；精确成本模型
  （parse/splice/diff 实测常数）留长期目标。tv80 实测：1.5% 编辑 67x、3.2% 编辑 23x、
  ~46% 合成用例回退全量（`test_large_change_falls_back_to_full`）。

## 调研：tree-sitter 的增量实现与阈值（2026-10-31，源码核对）

- **结论：tree-sitter 核心没有"改动占比阈值"**。`parser.c` 里没有按编辑大小的比例判断；
  常量只有 GLR 版本数（`MAX_VERSION_COUNT`/`MAX_VERSION_COUNT_OVERFLOW`）、错误代价
  （`MAX_COST_DIFFERENCE`）等，与编辑大小无关。
- **机制是结构性复用**：
  - `ts_tree_edit`（`lib/src/subtree.c::ts_subtree_edit`）按**字节区间与节点范围求交**，
    对受影响的节点置 `has_changes` 并重塑 padding/size；编辑区间之后的节点只平移、不清空。
  - 再解析时（`ts_parser_parse(old_tree, input)`）用 `reusable_node` 按 **byte_offset 对齐**
    遍历旧树；`ts_parser__reuse_node` 只在（位置相等 ∧ 无 `has_changes` ∧ 非 error/missing/fragile
    ∧ 外部扫描器状态一致 ∧ 无 included-range 差异）时整棵子树复用，否则下探/跳过/重新词法解析。
  - 大改动 ⇒ 大多数节点带 `has_changes` ⇒ 复用失败 ⇒ **自然退化为接近全量**（还多付复用尝试的
    簿记开销）。这正是"大改不如全量"的机制来源，但**没有显式比例开关**。
- **`ts_tree_get_changed_ranges`** 是**事后**比较新旧树（双游标，`get_changed_ranges.c`），返回
  "祖先链发生变化"的区间（官方注明可能比精确变更区略大），供高亮/查询等下游做失效——
  它是**消费者 API**，不是解析决策阈值。
- **对我们的取舍**：
  - 我们保留 `_max_change_ratio`（产品护栏，明确标注非 tree-sitter 对标）；它防的是并树
    一致性风险与"增量收益被摊薄"，不是复刻 tree-sitter。
  - 借鉴其 `changed_ranges`：`ReparseResult.changed_range` 输出变更 token 区间（新 token 坐标），
    供后续 check 增量失效/重渲染缩小范围（对应"编辑器接口"）。
  - 借鉴其"不可复用节点"规则：我们已用保守回退（多单元/首尾/符号门控/子集解析失败→全量）
    覆盖 error/缺口的同类风险。
- 来源：[`lib/src/parser.c`](https://github.com/tree-sitter/tree-sitter/blob/master/lib/src/parser.c)、
  [`lib/src/subtree.c`](https://github.com/tree-sitter/tree-sitter/blob/master/lib/src/subtree.c)、
  [`lib/src/reusable_node.h`](https://github.com/tree-sitter/tree-sitter/blob/master/lib/src/reusable_node.h)、
  [`lib/src/tree.c`](https://github.com/tree-sitter/tree-sitter/blob/master/lib/src/tree.c)、
  [`api.h`](https://github.com/tree-sitter/tree-sitter/blob/master/lib/include/tree_sitter/api.h)。
