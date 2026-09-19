# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## P1 — Verilog 实例完善

### P1.6 include 指令形态外置（预处理器外置线剩项）

预处理器形态外置已完成（形态 / 实参 / 后缀 / 处置策略 / 注释标点 / 续行 / 指令行切分），
仅剩 include 一处：

- `primitives/include.py` 的 `_INCLUDE_RE` / `_INCLUDE_ANGLE_RE` 硬编码
  `` `include ``（前缀 + 关键字拼写）与路径定界符 `"..."` / `<...>`；handler 还
  `del prefix, _name` 忽略调用方传入的声明值 → 语言包换前缀（或换语言）时 include
  静默失效。语料实测：138 样本里 `<...>` 形态 0 处、含 include 仅 2 文件（影响面窄）。
- 待定声明面（拟放**既有** `[directive_handlers.include]`，该表已有
  `enabled` / `search_dirs` / `silent`）：路径形态列表（开 / 闭 / 是否相对路径优先），
  关键字取用改走 `primitives/registry.py::split_directive`。

## 架构：精化（elaboration）部件化 + 插件化（未开工）

> 作者定调（2026-09-19）：精化器逻辑应由**插件**实现，引擎侧只留"加载精化器的位"。
> 本仓已有同款机制可复用，不造第二套：`core/component_protocol.md` §1 的
> `[capabilities]` 能力位 + `get_capability_in(name, rules_dir)`（按语言包作用域，
> 切语言不串用）；先例 `macro_policy`（引擎薄适配器 `preprocessor/macro_policy.py`
> + 插件 `plugins/macro_policy/`）与 `formatter`。

- **现状错配（实测，`analyzer/structure.py`）**：
  - 文本模式求值/判断（应 AST-first）：`_is_signal_expr` 正则、`render_subtree` 渲染
    后再字符串比较（`== port`）、`_eval_gen_cond` 的 `text.isdigit()` /
    `text.startswith(not_op)` / `IDENT_RE.fullmatch`、`_tokenize_const` +
    `_CONST_TOK_RE` + `_eval_const_expr` 文本递归下降、`_param_truth` 值文本判数字。
  - 语言知识硬编码（应进插件）：`_fill_body_ports` 的 `_FUNC_OR_TASK` 元组、
    `_fill_body_params` 的 `"ParamDeclStmt"` / `"Declarator"` / `"init"`、
    `elaborate_connections` 的 `field("connects") or "ports"`、
    `_fill_body_ports` 的 `or "direction"`，以及"名字在 `Node.content`"这一未声明形态假设。
  - AST 证据（`_drafts/probe_ast_shape.py`）：取反在 AST 里是
    `UnaryOp(op='!', operand=HierExpr([Identifier('W')]))`——**不是文本前缀**；
    `Number.value` 今天有 str / Node 两种形态（形态知识进插件后由插件自认，无需对齐语法绑定）。
- **契约划分**：引擎基座 = ①加载位（能力名 + 未声明降级为单文件 lint+analyze）
  ②产物模型与 `context.extra` 键名（**形状属引擎协议**——消费方是下游 postpass，
  不能由插件定义）③语言无关服务句柄（读源 / 宏展开 / AST 解析 / 行映射 `line_map`、
  宏区间 `macro_regions`）。插件 = 全部语言语义（实例化点→目标模块名、按名找定义文件、
  单文件精化、**AST-first 求值规则**、驱动源三类形态、层次穿透、端口方向语义）。
- **分期**：E1 立零件（`analyzer/elaboration/`：契约 + 能力名 + 加载位 + 产物模型 +
  句柄，只新增不接线）→ E2 verilog 精化器整体搬进
  `grammar/verilog/plugins/elaboration/`，门面改经契约调用并**同批删引擎侧旧实现与
  `[structure]` 声明**（不留双路径）→ E3 插件内 AST-first 重写（删文本解析链）→
  E4 文档收口（`core/component_protocol.md` 加"精化器能力位"节 + 插件 README +
  `MODEL_INDEX`/`analyzer/README`）。
- 按建议定的两条：编排骨架（发现循环 / 汇总 / `extra` 注入）**留引擎**（无语言语义）；
  产物**运行期核验**（照 transform 插件 `produces` + `_verify_produced` 同款，
  少填产物键 → fail，不让下游静默空转）。
- 外部对照（为什么这不是过度泛化）：elaboration 是 HDL/EDA 的必备阶段（Verilator
  `V3Param` 删未选中 AST 子树、slang `Elaborator`、VHDL/Ada LRM 专章），通用语言侧
  同构概念（Racket phase、Scala macro elaboration、Zig comptime、C++ 模板实例化）；
  成熟实现一律在 AST/IR 上精化，文本只作输出与诊断呈现。注意中文"精化"与
  refinement（B/Event-B 规格精化）撞词，部件/配置名用 `elaboration`。


## 外部审计修复（Bifrost 全仓诊断，2026-09-18 起）

> 清单与处置记录：`_drafts/bifrost/findings.md`、`_drafts/bifrost/dispositions.md`
> （工作草稿，不进 git）。范围按作者定调：只修非 tests；每批跑 smoke +
> `check_doc_refs` + `check_hardcode`，批末跑全量测试。完成即删对应条目。

- **B-B 复杂度/长方法重构**（大改，分部件分批；按局部→全体逐个单元做）：
  - ✅ `grammar/verilog/plugins/formatter/boundary.py::build_block_tokens`（249 行 / CC 79）
    已按字段拆为六个模块级助手（`308651b`）。
  - ✅ 同文件 `BoundaryScanner._scan_tokens`（319 行 / CC 67）：已引 `_ScanState` 收拢
    16 个状态量，拆为三块 handler + 换行判定链/分派分支的小函数（`_scan_tokens` 319 → 35 行）。
  - ✅ `lexer/main_lexer.Lexer.tokenize`（397 行）：已引 `_LexState` + 逐分支提方法
    （12 个 `_scan_*`），`tokenize` 397 → 56 行。
  - ✅ `parser/pratt_parser.parse_expression`（310 行）：已引 `_PrattCtx` 收拢上下文
    （对外签名不变），主体拆为前缀/中缀两块各步，310 → 45 行。
  - ✅ `analyzer/structure.py::_build_signal_graph`（257 行 / CC≈109）：已引
    `_SignalGraphCtx` + 端口穿透两方法 + per-file 三分派，257 → 装配（`35ccbff`）。
  - ✅ 同文件 `_precompute_generate_active`（81 行 / CC 21）+ 成对填充去重
    + `_eval_const_expr`（112 行 / CC 28）→ `_ConstExprParser`：B-B4b；
    信号图三层方法的 CC 二次收口（三类裸源 / 过程块两趟 / 连接两类）：B-B4b2。
  - ⏳ 同文件 `_StructureBase` 上帝对象（类体 1110 行 / 53 成员 / 43 方法）：
    层 3 精化基类，被 `ProjectChecker` 继承、postpass 经 `context.extra` 消费；
    拆类需先立 ADR（B-B4c，暂缓）。
  - ✅ `lexer/main_lexer.Lexer.__init__`（175 行）：已拆为装配 + 七个分步方法
    （`de22813`）——类级最大函数 175 → 56 行。
  - ✅ **第二梯队全部完成**（B-B6..B-B15，逐单元验证 + 提交）：
    `ConfigRegistry._resolve_decls`(142) / `_load_meta_declarations`(118) /
    `load_user_check_config`(91) / `GrammarRule.__init__`(79) /
    `ProjectChecker.check`(65) / `build_suppress_map`(60) /
    `AnalysisTraversal._walk_node`(47) / `_glob_match`(43) /
    `_validate_node_specs`(43) / `load_all_toml`(70)。
  - ✅ **第三梯队全部完成**（方法级 >80 行，B-B16..B-B25 逐单元验证 + 提交）：
    - `renderer/primitives/join.py::eval_join`（193）→ `_JoinCfg` +
      渲染/组装/槽清理/包裹分步（`6452ce6`）。
    - `linter/discovery.py::Discovery._discover_range`（177）→ 四路分派
      + `_rule_of`/`_make_stmt_node`（`feb1bb5`）。
    - `lexer/number_gen.py::compile_number_pattern`（174）→
      `_PatternBuilder` 装配器 + 四阶段（`eb865cc`）。
    - `renderer/inline_comment.py::restore_line_comments`（169 → 73）→ 四条落位
      路径各自成对（`b58a3b5`）；同文件 `restore_comments`（139 → 65）→
      锚点窗口/插入/退化/占位四块，与前者共用记账助手（`57cf50c`）。
    - `lexer/capture_runner.py::CaptureRunner.run`（132 → 31）→ kind → handler
      分发表，`_VALID_KINDS` 改由该表派生（`c4e9ddb`）。
    - `renderer/node_renderer.py::render_node`（108 → 46）→ head/body/tail 三段
      + verbatim 直出 + LineSuffix 取出（`710db10`）。
    - `renderer/doc.py::_best`（96 → 63）与 `_fits`（87 → 41）→ 各抽多行分支
      （`_best_concat`/`_best_union`/`_row_width`/`_fits_concat`）（`12bca10`）。
    - `renderer/primitives/line.py::eval_line`（83 → 33）→ `_LineState` +
      断行/元素/锚插入分派（`8da55be`）。
    - `renderer/primitives/join.py::_assemble_join`（102 → 33，B-B16 拆分时
      转移出来的长方法，本次收口）（`8ff6ad6`）。
    - ⚠ **复查口径修正（2026-09-20）**：`report_long_method_and_god_object_smells`
      **每调用最多分析 25 个文件**（报表头 `Files analyzed cap: 25`，**不报截断**）——
      历轮复查脚本用 `CHUNK=60` → 约 58% 文件静默漏检。脚本已改 `CHUNK=20`。
      - **函数级 >80 行 = 5 处**（旧结论"命中 0"**作废**；AST 独立复核一致）：
        `preprocessor/_expand.expand_tokens` 113（CC 7）、
        `formatter/__init__.build_engine` 107（CC 6）、
        `linter/scanner.LinterScanner.scan` 106（CC 10）、
        `pipeline/__init__.run_pipeline_on_source` 101（CC 9）、
        `linter/scanner.LinterScanner.__init__` 93（CC 8）——均刚过线，CC 不超阈。
      - **类/容器级 17 处**（旧结论"9 处"**作废**），见下条。
      - 参照：`compute_cyclomatic_complexity` / `compute_cognitive_complexity` **无上限**
        （CHUNK 60 与 20 结果一致）→ B-F 的 "CC 12 / 认知 5" **仍有效**；
        `report_structural_clone_smells` 无上限提示，但分块会影响"最佳克隆对"选取
        （36 文件一次 46 条 vs 18+18 两次 52 条）→ 重复对数须**固定分块**比较。
    60-80 行区间现有 9 项（`renderer/doc._best` 63、`node_renderer.render_body` 77、
    `capture_runner.build_rules` 79、`lookahead._level1_scan` 77 等）——均低于阈值，
    其中分派型函数（`_best` 15 个变体分支）刻意不再拆。
  - ⏳ **类级上帝对象 17 处命中**（2026-09-20 修正版；需设计决策，非机械拆分）：
    **(A) 类体 >300 行 —— 10 个（正是全仓 class body >300 行的全部）**：
    `RuleMatcher` 914 行/36 方法（354）、`Lexer` 886/57（424）、`Discovery` 700/34（234）、
    `BoundaryScanner` 549/30（241）、`Parser` 494/25（246）、`_C4Compiler` 480/39（195）、
    `LookaheadTable` 454/20（154）、`ConfigRegistry` 445/16（127）、
    `SignalGraphBuilder` 404/22（98）、`GrammarRule` 327/18（102）。
    **(B) 仅成员/函数数触发（行数 <300）—— 7 个，多为上下文/状态容器**：
    `_PipelineContext` 77 行/49 成员（73）、`AnalysisTraversal` 239/29（33）、
    `ParseContext` 74/22（19）、`StructureCtx` 121/21（17）、`_ScanState` 33/21（17）、
    `LinterScanner` 235/20（15）、`ModuleExtractor` 272/15 函数（15）。
    判别（全仓 139 个类：类体中位数 21 行、P90 224、P95 454）：(A) 组确属 P95–P99
    尾巴，但**类内无坏味道**（最长方法 30–79 行、最大 CC 6–13，CC 族对这些类零命中），
    且多为"**模块即类**"（`RuleMatcher` 类体占文件 92%、`Lexer` 88%、`Discovery` 91%）
    →读作"这个模块很大"更准确；(B) 组是**判据假阳性**（上下文/状态容器天生成员多，
    `_ScanState` 33 行 21 字段即为此存在）。其中 `SignalGraphBuilder` / `StructureCtx` /
    `ModuleExtractor` 是 B-B4c 拆 1129 行 `_StructureBase` 的**产物**（1 个巨型命中 →
    3 个中等命中，方法级因此变干净）。信号明细见 dispositions 的类级表。
  - ✅ **`_StructureBase` 上帝对象已解（B-B4c-0..7，2026-09-19）**：先删 3 个门面
    不可达方法（-49 行），再把 49 个方法按职责组合化——`StructureCtx`（会话状态 +
    协议读取 + 2 个共享读取助手）+ 6 个协作者（`GenerateEvaluator` 151 /
    `ConnectionElaborator` 140 / `ModuleExtractor` 200 / `FilePipeline` 151 /
    `ModuleIndexer` 72 / `SignalGraphBuilder` 361），门面 `ProjectChecker` 不再继承、
    改为**组合根**接线。**最大类 1129 → 361 行**（外部裁判类级命中相应消失）；
    依据与理由写在 `analyzer/structure.py` 模块头（一个子类零覆盖 / 9 字段收 ctx /
    簇间无反向边）。
- **B-C 结构重复**（非 tests 111 组，按"同文件/同部件 → 跨部件"递进）：
  - ✅ 引擎侧同形重复：`_deep_merge` ×2、`get_config_refs` ×4、`plugin_loader`
    合并型 getter ×5、`_serialize_member`/`_serialize_group`、`soft_break` 三态
    原语（`d2a6cbe`）。
  - ✅ 检查插件族 AST 助手：`_iter_nodes` ×6 / `_unwrap` ×3 / `_target_sig` ×2 /
    `_const_value` ×2 → `core/define`（引擎）+ `checks/_shared.py`（语言侧）
    （`83b350b`）。
  - ✅ `typed_ports` 组件内 `_text` ×3 / `_collect_type_scopes` ×2 →
    `typed_ports/_node_utils.py`（`616ce1b`）。
  - ✅ 常量表达式求值两份 78 行逐字同体 → `checks/_shared.const_eval`（`6262314`）。
  - ✅ `formatter/passes` 行首缩进量化三份同体 → `formatter/style.line_indent_width`；
    检查族跨插件小助手（`_is_timing_always`、`_is_parameterized` 系）→
    `checks/_shared`（`4f0ad2c`）。
  - ✅ 三处同文件同体：`handle_ifdef`/`handle_ifndef`、
    `config_registry.resolve`/`resolve_with_sources`、
    `renderer/doc._has_break`/`_has_hardline`（`cfc5944`）；另修掉 B-B2 拆分后
    新显影的 `Lexer._scan_number`/`_scan_unsized_number` 同体。
  - ✅ 3–5 行样板体两对：linter `_skip`（matcher 4 处内联/封套 + discovery 2 处）
    → `core/token_protocol.skip_trivia`（TRIVIA 判定与跳过同源）；parser
    `_get_block_end_for`/`_get_block_end` 逐字同体 → `core.define.block_end_of`
    （`2ac9f2f`、`d80f330`）。
  - ⚠ 复查（外部裁判，同口径分块）：非 tests 重复对 **111 → 108**（2026-09-20 同参数
    `min_score=90` 重测；84 对 ≤40 token = 薄入口/桩型）。**此前记的 "69 对" 是 B-D
    分类期的中间快照**——复杂度批次（B-F 六~十）拆出大量薄助手后回升，属 C 类
    "具名入口 → 共享实现"形态（共性已抽、残留入口样板），但**结案前需按 A–G 重新归位
    一次（逐对确认无新形态）**：这一步未做，故 B-C 现状是"判据已定、快照待重跑"。
    分类明细见 dispositions（含 token 量下降：159→35、234→52、156→20 等）。
  - ✅ 类内 1 对 `StructureCtx.field` ↔ `rule`（30 tok）：**已判保持**（B-B4c 完成后
    可直接判——两者读**不同来源**：`rule` 取 `[structure]` 顶层键、`field` 取 `fields`
    段键；共性只剩 `str(x or "")` 骨架，合并要把来源字典当参数传，与"一来源一入口"
    判据相反）。policy 3 对已定：保持（两道门禁各自独立、可单跑，抽公共会把门禁耦合，
    且脚本是制度执行者非产品代码）。
- **B-E 内置策略（性能类 in-loop 族）**：AST 自查当前非 tests 树共 12 处"循环内 I/O"
  （原始报数行号已随重构漂移，按形态重定位）。
  - ✅ `analyzer/structure.py::ModuleIndexer` 目录兜底查找：原实现对每个未解析单元名
    重读整个目录（全语料实测 15 次查找 / 13 次未命中 = 整目录读 13 遍、134 次读 / 95 ms）
    → 改按目录建一次「单元名 → 文件」文本索引（`ctx.dir_module_files`，随会话失效）
    → **18 次读**；加回归测试锁"按目录建一次"（诱饵计数：1 vs 关缓存 3）。
    外部裁判同口径复查：命中数不变——策略报的是**形态**（"循环里有读文件"仍在，
    即建表循环），病理（同一文件反复读）已由读数证明消失。
  - ✅ 其余 11 处判**保持**（逐文件各读一次，非病理）：`parse_file`、`load_check_rules`、
    `_plugin_declarations`/`_load_decl_value`、`_apply_check_suppressions`、
    `_stage_render`（写 extra）、`collect_grammar_keywords`、`load_layouts`、
    `cmd_rename`、`_smoke_test`（format/lint/check 三面必跑）、
    `bifrost_probe/smelly.py`（**刻意坏味探针**，修好即门禁失效）。判据与逐条理由见
    dispositions。
- **B-F 圈复杂度 / 认知复杂度**（九个批次，2026-09-20）：外部裁判同口径量化（批次三起
  把本机 `.agents/` 技能脚本排除出扫描集，历史数字同口径扣除）——  批次一 150 → 132 / 157 → 140；二 132 → 124 / 140 → 135；三 124 → 107 / 135 → 117；
  四 107 → 87 / 117 → 96；五 87 → 78 / 96 → 90；六 78 → 58 / 90 → 72；
  七 58 → 42 / 72 → 49；八 42 → 28 / 49 → 33；九 **28 → 17 / 33 → 21**；
  **九批合计 CC 150 → 17（-133）、认知 157 → 21（-136）**；剩下的命中已全部落在
  “已判保持”清单内，只余少量新露出的小项（见下）。
  - ✅ 已清（**整文件**）：`linter/lookahead.py`、`preprocessor/_expand.py`、`parser/follow.py`、
    `transform/config_driven.py`、`pipeline/__init__.py`、`formatter/indent.py`、
    `width_check/_width_check.py`、`formatter/wrap.py`、`formatter/passes/column_align.py`、
    `renderer/node_renderer.py`、`parser/grammar_inject.py`、`linter/checkers/matcher.py`、
    `parser/attribute_binder.py`、`parser/_production.py`、`pipeline/schedule.py`、
    `typed_ports/_transform.py`、`checks/_shared.py`、`latch_check/_latch_check.py`、
    `core/plugin_loader.py`、`pipeline/units.py`、`parser/rule_selector.py`、
    `transform/engine.py`、`linter/grammar_slicer.py`、`core/global_state.py`、
    `preprocessor/_bridge.py`、`analyzer/primitives/_symbol.py`、`pipeline/report_html.py`、
    `linter/scanner.py`、`main.py`、`analyzer/structure.py`、`transform/primitives/node.py`、
    `lexer/number_gen.py`、`hier_check/_hier_check.py`、`formatter/passes/ifdef.py` + 
    `ifdef_annotate.py`、`formatter/grouping.py`、`transform/slot_runner.py`、
    `analyzer/report_html.py`、`linter/discovery.py`、`lexer/pre_scan.py`、
    `lexer/number_runner.py`、`linter/checkers/macro_hygiene.py`、
    `typed_ports/_check.py`、`formatter/passes/inst_port.py`、`tools/config_sites.py`、
    `policy/check_doc_refs.py`、`policy/doc_sync.py`、`tools/check_test_isolation.py`、
    `tools/check_coverage_delta.py`、`parser/parser_core.py`、`lexer/capture_runner.py`、
    `lexer/main_lexer.py`、`parser/pratt_parser.py`、`preprocessor/macro_shape.py`、
    `core/define.py`、`core/config_registry.py`、`renderer/fidelity.py`、
    `tools/check_gate_efficacy.py`（批次十追加）`renderer/loader.py`、
    `renderer/primitives/join.py`、`renderer/primitives/opt.py` + `ref.py`、
    `inst_check/_inst_check.py`、`name_check/rules/_prefix_suffix_check.py`、
    `analyzer/suppress.py`、`analyzer/checks.py`、`parser/block_parser.py`、
    `parser/__init__.py`、`grammar/c4/plugins/asm_gen/_asm.py`、
    `formatter/__init__.py`、`formatter/boundary.py`、`linter/checkers/style.py`、
    `linter/checkers/boundary.py`、`case_check/_case_check.py`、`policy/check_hardcode.py`；
    局部：`transform/_semantic_mapping`（认知 99 + CC 27）、
    `normalizer._normalize`（34/89）、`renderer/doc` 三处（24/62、11/17、16/27）。
    提交见 dispositions 的逐条记录。
  - 判据 = **分派型保持 / 有内部逻辑拆**（判据与逐条清点在
    `_drafts/bifrost/dispositions.md`「CC / 认知复杂度三分类」）：`renderer/doc.flatten`
    20/18、`_best` 17/16、`_doc_has_break`/`_flat_w`/`_fits`/`_drop_break_after_hardbreak`
    属"一变体一臂"分派型，**刻意不拆**（拆散语义、可读性反向）。
  - 两条方法论（已写进 dispositions）：①trace/闭包提成 `_trace_printer(trace)` 参数化
    （一次去掉多处 `if trace:`；循环内 `sorted()` 打印留 guard）；
    ②状态收 `_XxxCtx` dataclass 后助手提到模块级——**嵌套函数的分支计入外层 CC**，
    所以"提模块级"是硬要求不是偏好。
  - ⏳ 剩项：**无**。批次十把批次九队列的 12 项一次做完，并顺带清掉全库复检新露出的
    6 项（`renderer/primitives/opt.eval_opt`、`ref.eval_ref`、`formatter.split_port_close_lines`、
    `linter/checkers/boundary.BoundaryChecker.validate`、`parser._apply_ext_injections`、
    `formatter/boundary._collect_call_names`——最后一项原记“待判是否并入判保持”，
    实证可拆，故**不**并入）。复检剩余命中**全部**在下方“已判保持”清单内。
  - ⛔ **已判保持，不得重开**：`boundary._build_scope_kind_map` 21/52 与 `_resolve_first_tokens` /
    `_collect_stmt_headers` / `_collect_block_rule_bounds` / `_is_case_item_token`（“逐规则/
    逐元素判定的单一职责循环，再拆只会把映射逻辑碎片化”）；`renderer/doc.flatten` 20、
    `_best` 17、`_doc_has_break` / `_flat_w` / `_fits` / `_drop_break_after_hardbreak`、
    `parser/rule_selector.serialize_production_tree` 12（一变体一臂的分派型，臂内一行）。
    逐条理由见 dispositions。
  - 批次验证（批次九 8 提交）：全量 `pytest tests/ -n 4` **2111 passed / 7 skipped**；
    诊断基线 5548 持平；`eval_lint_accuracy` 33/33 + 0 误报；三门禁 PASS；字节对拍
    73 文件 0 差异。
  - 批次十（13 提交）：**CC 17 → 12、认知 21 → 5**；十批累计 **CC 150 → 12（-138）、
    认知 157 → 5（-152）**。验证同口径全绿：全量 `pytest tests/ -n 4` **2111 passed /
    7 skipped**；诊断基线 5548 持平；`eval_lint_accuracy` 33/33 + 0 误报；三门禁 PASS；
    字节对拍 73 文件 0 差异；13 个改动文件 Pylance 0 诊断。**本主线收口**。
  - 拆法新增三则（写进 dispositions）：③平臂 if/elif 链在 Bifrost 口径下便宜、
    臂内嵌套贵 → 优先“臂体挪进助手”而非改分派表（探针实证）；④多来源 doc 收集用
    累加器 `parts`，别让助手各返回 `Concat` 再拼（改变 Doc 嵌套结构）；⑤状态收
    dataclass 三形态：扫描游标（`_IntervalScan` / `_BoundaryScan`）、跨调用作用域
    （`_RuleScope`）、行/项事实束（`_LineFacts` / `_PortFields`）。

- **结构欠账的度量与停止判据**（2026-09-20 立）：外部裁判按阈值报命中 → 建议无穷；
  改为**超额量口径 + 一个标量**，判据全文见 `policy/structural_budget.md`，度量用
  `tools/structural_score.py`（`--save` 冻结基线 / `--compare` 新增即回归）。
  基线（2026-09-20）：**S = 1595**（C 复杂度 119 / L 规模 536 / D 重复 940），
  规则过滤后"必须处理"清单只有 13+5+4+20 项（C 分量的 18 项里 12 项已在"判保持"
  清单 → 实际待做 ≈ 6 项）。核心规则：R1 内部线 = 阈值×1.5、R2 模块即类豁免、
  R3 重复实体门槛（≤40 tok 算入口样板）、R4 制度执行者豁免、R5 按 churn×complexity 排序。
  决策：`ROI = ΔS / 改动行数`，**ROI < 0.05 不做**（起始标定，两次实测后定稿）。

- **B-G 测试断言族**（`report_test_assertion_smells`，起点 22 项，2026-09-20 逐项判完）：
  ✅ **22/22 判保持**——本族在本仓无语义问题，信号来自"断言不在被测函数体内"的词法
  判据：19 项断言/校验在调用链内（`_assert_ok` / `_module_body` /
  `_assert_comment_kept_standalone` / `_run` / `check_engine_compat` 的
  `raise ConfigError` / `validate_sequence` 的 `raise ValueError` / `assert_clean`）、
  2 项是"不抛即通过"的健壮性与安全网测试、1 项 `self-comparison` 是两次独立求值
  （同种子可复现判据）。逐项证据见 dispositions；无改动。

> 审计外观察（不在本清单）：无。此前记的 "`_eval_gen_cond` 的 `!PARAM` 特判是 Verilog
> 形态进了引擎"已修（generate 条件面的规则/字段/运算符拼写全部移入 `[structure]`
> 声明，引擎零 Verilog 形态）——口径收窄后的**求值能力**边界记在
> `docs/gaps/gap-semantic-elaboration-boundaries.md` 边界 1/2。

## 语言知识渗透复审与精化基座重设计（2026-09-20 立，长期）

> 作者定调：**近期主线 = 完成 Bifrost 审计修复**（顺序：20 对重复 → 接口收窄
> 70+27 项 → 统一抽象 ~4 项 → 拆模块 4 项；判据与门限见 `policy/structural_budget.md`）。
> 下面两条是之后的事，先在档上，不在近期排期。

### L1 语言知识渗透复审（长期，方法待定）

- **已知的机械化探针（现有的两条，只覆盖"词法面"）**：
  - `policy/check_hardcode.py`：grammar/ 提取的关键字出现在引擎代码即报（词表法）
  - `tools/config_sites.py check`：引擎读的配置键是否都在语言包声明（配置面漂移）
  - → 两条都抓不到"**结构/语义形态**渗透"（如引擎侧自己实现了一套端口/宽度/信号图语义）
- **候选机械化方法（不引语言包、避多语言互渗）：声明面缺失探针**——临时从语言包
  删除一段声明（某字段/某规则形态），跑全量测试：**仍绿的部分就是引擎在替语言包做事**。
  风险低（不动语言、只动声明面，可回滚）、可脚本化；与 `tools/check_gate_efficacy.py`
  （事故变异期望变红）同构。
- **"多加语言包"作为暴露法的代价（已知事实）**：c4/yaml 覆盖浅，暴露力有限；
  且多语言同进程已有真实串味史（`_PIPELINE_SHARED` 按 rules_dir 缓存、
  `global_state` 语言注册面只增不还原、`test_language_switch` 曾偶发失败）→ 该法
  只在隔离跑（每语言一进程）下可用，不作日常手段。
- **状态**：方向已定（作者 2026-09-20），方法待选；未见排期。

### L2 精化基座重设计（引擎 vs 插件的能力边界）

- **作者定调（2026-09-20）**：重设计一次基座，**引擎只留"普适的文件操作 + 树化行为"**；
  把**抽取能力**（从树上取语言结构）与**动态求解**（常量/宽度/端口方向等语义求值）
  移到插件侧。现状是基座把**很多 Verilog 独有的操作在引擎内侧实现了**——作者判定为
  "明显的语义渗透"。
- **已知命中点（本仓实测事实，非推测）**：
  - `analyzer/structure.py`：引擎侧实现了 generate 条件求值（`_eval_const_expr`/`_ConstExprParser`）、
    端口/参数抽取（`_PortFields`/`ModuleExtractor`）、信号图（`SignalGraphBuilder`）
  - 数字形态：`NumberFSM` 全局硬编码单例同时承载 C 与 Verilog 形态（roadmap P2.1 已记）
  - 对照：`typed_ports` 已是"抽取走插件"的正面样板（插件 + TOML 声明，引擎零硬编码）
- **已有约束须一并遵守**：语言知识零进代码（AGENTS 硬约束）、不留兼容垫片、
  删除先证后删（`policy/doc-alignment.md`）；配置加载 fail-fast。
- **预期待定**：属架构决策，动手前先立 ADR（`docs/decisions/`）；现仅记方向与命中点。

## 测试基础设施

- **并行度默认值**：`pyproject.toml` 的 `addopts = "-n auto"` **保持现状**（作者
  2026-09-19 定调“先这样”）。本机跑全量时自行显式传 `-n 4` 规避顶满核（做法与分档
  见 `tests/README.md`「改动节奏分档」）；不改仓库默认。
- **全量并行跑偶发失败（预存在，成因未定）**：`tests/engine/core/test_language_switch.py::
  test_plugin_scope_excludes_other_language`——切到 verilog 后 `active_plugin_classes()`
  仍含 c4 的 `AsmGenPlugin`。实测：带/不带 2026-09-18 那批改动都会出现（3 跑 2  败 / 2 跑 1 败）
  → 非该批引入；单跑与 `-n0` 不复现；`PYTHONHASHSEED` 0..7 全过；
  `tools/check_test_isolation.py` 160 OK / 0 FAIL。待定位：并行 worker 下
  `_components_initialized` / `_active_components` / `_plugin_origins` 三者何时 不同步。
  **排期（作者 2026-09-19）**：等 bifrost 审查主线走完再单独开单元查；在此之前全量
  门禁如因此抖动，按 partial 报（不得当“随机噪声”扫掉）。
