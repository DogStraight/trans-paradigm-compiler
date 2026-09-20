# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

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
  基线（2026-09-20）：**S = 1595**（C 复杂度 119 / L 规模 536 / D 重复 940）→
  终态 **S = 0**。下落分**三类**记：**代码收益** = 重复逻辑合并（D 940 → 0，2 对真重复）
  + 文件变短（L 536 → 528）+ 死代码删除 7 项；**口径闭合** = C 的 19 项 + L 的 4 项逐项下结论
  + D 的 3 对同形不同源（登记 `structural_kept.json`）——后者不是复杂度下降。
  核心规则：R1 内部线 = 阈值×1.5、R2 模块即类豁免、R3 重复实体门槛（≤40 tok 算入口样板）、
  R4 制度执行者豁免、R5 按 churn×complexity 排序、R6 判保持登记（对全族生效，每条必写理由）。
  决策：`ROI = ΔS / 改动行数`，**ROI < 0.05 不做**；⚠ 不进 S 的杠杆（简化接口）不适用该公式，
  另立判据：**公开名在本文件外零引用即降私有；若连需求都没有（无调用/无声明/无文档）直接删**。

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

> 作者定调：**近期主线 = 完成 Bifrost 审计修复**——**已收口**（2026-09-20）：重复族 ✅
> → 复杂度族 ✅ → 接口收窄 48 项 ✅（47 降私有 / 1 删）+ 死代码 7 项 ✅ + 模块规模 4 项 ✅
> （低认知大容器 → 保持）。判据与门限见 `policy/structural_budget.md`，当前基线
> **S = 0**（每个命中都有结论；原始量仍在，删 `structural_kept.json` 对应条目即可回滚）。
> 下面两条是之后的长期方向，不在近期排期。

### L1 语言知识渗透复审（长期）

- **范围（作者 2026-09-20 指定）**：**重点 analyzer / preprocessor / linter**；
  parser 与 lexer 基本形式化、renderer 主要吃原语、transform 是插槽形式（可能性小）
  ——但**实测校正**：parser 仍有一处分量级渗透（位宽字面量，见下）。
- **判据三条（强弱递减；详见 `docs/gaps/gap-language-penetration.md`）**：
  ① **最小语言包探针**（主判据，行为面）——只加载最小骨架包跑全量测试，仍绿的引擎
     测试 = 普适面；② **声明面缺失探针**（辅助，行为面）——临时删一段语言包声明跑测试，
     仍绿处 = 引擎替声明做事；③ **弱信号面** = `tools/lang_penetration.py`
     （引擎里出现语言包规则/节点名（硬信号）/ 语言对象词作标识符（弱信号，须人工判））。
  ⚠ 三条都只覆盖**被测路径** → 结论只能是"已知渗透面收敛"。
- **首轮实测（2026-09-20，词法/结构面；全表见 gap 档）**
  - **analyzer = 重灾区**（与作者判断一致）：`structure.py` 硬编码 5 个**规则名**
    （`"FuncDecl"/"FuncDeclOld"/"TaskDecl"`、`"ParamDeclStmt"`、`"Declarator"`）
    + 语义名词标识符 **183 处**（端口/实例/信号驱动）；`checker.py` 的 `_signal_graph`/
    `inst_sites`。**均归 L2（精化基座）**——不动，等 L1 其余面做完。
  - **parser**：11 处结构名命中全是**引擎表达式树/节点协议名**；原先当渗透的
    `_parse_bit_width_literal` 经**调用计数探针**实测在三语言包下**不可达**（lexer 按
    `[[number.based]]` 捕成单 token，规则的 `Number` 先手接住）→ 实为**冗余第二路径**，
    **已删**（钩子 + 槽位 + 登记条目）。
  - **pipeline**：`__init__.py` 曾按名调语言包的排版步骤（`split_port_close_lines` /
    `split_inst_tail_lines`）→ **已修**：能力面改声明 `pre_scan_passes`（前置文本遍列表）。
  - **linter / preprocessor / lexer / renderer / core / transform**：词法/结构面未发现活渗透
    （linter 的 21 处、renderer 的 18 处、lexer 的 7 处名词命中全是误报；
    `core/_protocol.py` 的 `ATTR_RESOLVED_PORTS` 等是**产物契约键名**，按既定决策留引擎 → 归 L2 重审）。
  - **同名陷阱**：`Root`/`Comment`/`UnaryOp`/`BinaryOp`/`TernaryOp`/`Number`/`Identifier`/
    `MacroCall` 是**引擎表达式树/节点协议**（语言包按此名声明 renderer），不是渗透。
  - ⚠⚠ **新判据（当场踩坑得出）**：弱信号命中要过四道——① 词法命中 → ② 看调用链定性
    → ③ **数调用次数（可达性）** → ④ 才分“渗透 / 死代码 / 契约”。
    只做到 ② 会把**不可达的冗余路径**当渗透，白花一道外置工序（本次实测）。
- **现有的两条门禁只覆盖词法面**（关键字字面量 / 配置键声明），为何抓不到语义渗透：
  用配置键或通用算法表达的 Verilog 语义里**一个 Verilog 词都没有** → 形式完全合规；
  配置点位法反而**奖励**这类渗透。两条门禁答的是"有没有**语言的关键字**"，
  而精化基座的问题是"有没有实现**语言的语义**"——前者是字符串问题，后者是判据问题。
- **下一步**：① 语言包 `BitWidthLiteral` 规则**待拍板是否删**（实测六种形态均不可达，
  连带 renderer layout 与 `inst_check`/`width_check` 的该节点名分支同属死面）；
  ② 行为面基线（最小语言包探针）——判语义面的唯一办法，单独一期；
  ③ 之后就进 L2（精化基座重设计；analyzer 的 5 个规则名 + 183 处语义面 + 产物契约键名都在那一批）。
- **另："多加语言包"作为暴露法的代价（已知事实）**：c4/yaml 覆盖浅，暴露力有限；
  且多语言同进程已有真实串味史（`_PIPELINE_SHARED` 按 rules_dir 缓存、
  `global_state` 语言注册面只增不还原、`test_language_switch` 曾偶发失败）→ 该法
  只在隔离跑（每语言一进程）下可用，不作日常手段。
- **状态**：方向已定（作者 2026-09-20），方法待选；未见排期。

### L2 精化基座重设计（引擎 vs 插件的能力边界）

- **作者定调（2026-09-20）**：重设计一次基座，**引擎只留"普适的文件操作 + 树化行为"**；
  把**抽取能力**（从树上取语言结构）与**动态求解**（常量/宽度/端口方向等语义求值）
  移到插件侧。现状是基座把**很多 Verilog 独有的操作在引擎内侧实现了**——作者判定为
  "明显的语义渗透"。
- **设计原则细化（作者 2026-09-20，防止走成"普适化 → 配置面膨胀"）**：
  **自带配置的增量设计**——引擎侧留**占位 + 简单实现**（能跑通最普适形态），
  语言特有的完整实现**集中到语言适配层**；这样配置复杂度与语言知识都落在插件侧，
  插件又靠引擎的原语组合而不必重复造骨架。
  - **三选一别走错**：引擎硬编码（禁） / **引擎配置字段（慎）** / **插件实现（首选）**。
    "为让引擎普适而设计一套 schema"会把复杂度从代码搬到配置，并为新形态预留表达力
    缺口——这是本仓已经踩过的形态（见下面的数字实证）。
  - **两条判据**：① *普适性*：去掉所有语言包声明后，引擎的简单实现能否对任意输入
    给出**可解释**结果？能 → 引擎；不能 → 插件。② *配置 vs 代码*：**能被表单穷举、
    且不涉及算法/状态机/语义求值**的少量变体 → 留配置；需要算法/状态机/求解的 →
    移插件代码。③ *增量*：插件只写"与默认的差"（override / 扩展点），不复制骨架。
  - **取舍的定位（作者 2026-09-20）**：声明式表达一切 ⇒ 配置面无限；不可能。所以做法是
    **把"会变动的结构"做成配置，把"特异的部分"做成语言包代码**——不是消灭取舍，
    而是把取舍**局部化**（每个决定只影响一个组件、可回滚、可被测试锁住）。
  - **把"会变动 vs 特异"变成可判的第三判据（看它在语言间的分布）**：
    | 语言间分布 | 归宿 |
    |---|---|
    | 多语言共有、且形态稳定（只有值不同） | **配置**（值走声明） |
    | 多语言共有、且结构一致（形态相同） | **引擎骨架**（上提，避免各语言复制声明） |
    | 单语言特有，或各语言形态各异 | **插件代码**（下沉） |
  - **两个可机械测的失效信号（用来发现"放错了"）**：① *该上提却还在配置*：同一 schema 下
    多个语言包的声明高度相似（复制粘贴式）→ 说明这是共性结构，应上提为骨架/默认；
    ② *该上提却还重复*：同一段逻辑出现在 ≥2 个语言包，或插件与引擎默认逐字同体
    （Bifrost 重复工具 + 现有 A–C 类判据可测）→ 应上提。两条都是**往返通道**：
    只能单向移动（一味下沉或一味上提）会累积另一种债。
- **普适原语必须共享**（否则各插件重写"跳空白"之类会漂移）：既有 `core/token_protocol`、
    `lexer/lexer_utils`、`core.define.iter_nodes` 已是这类原语，重设计时明确清单。
- **命中点与实证（本仓事实）**：
  - `analyzer/structure.py`：引擎侧实现了 generate 条件求值（`_eval_const_expr`/
    `_ConstExprParser`）、端口/参数抽取（`_PortFields`/`ModuleExtractor`）、
    信号图（`SignalGraphBuilder`）→ 属"抽取 + 动态求解"，是 L2 的首要搬迁面。
  - **数字形态（配置面膨胀的实证）**：旧 `NumberFSM` 硬编码单例**已不存在**
    （P2.1 配置化时移除，`lexer/main_lexer.py` 有记录）。现状是另一种形态——
    为让引擎普适，`grammar/verilog/base/_number.toml` 用 **7 个字段 × 4 个形态块**
    （`size.digits`/`base_prefix`/`signed`/`bases`/`value_digits`/`value_allow`/
    `value_allow_space`）声明形态，引擎侧 `number_gen._PatternBuilder`（通用 DFA
    构造）+ `number_runner` 把它编译成状态表。**加形态可能撞 schema 表达力边界**，
    这正是"普适化推高配置面"的样本。按新原则应改为：引擎留"十进制/浮点最简扫描"
    占位 + 数字扫描原语（字符类判定 / 最长匹配 / radix 取值），verilog 插件侧
    集中实现位宽·进制·x-z 形态。
  - 正面样板：`typed_ports`（抽取走插件 + TOML 声明，引擎零硬编码）。
- **诚实代价（写进 ADR 权衡）**：声明式 → 命令式后，**加语言不再是零代码**
  （c4/yaml 需写一小段插件或继承默认）；换来的是引擎 schema 与代码不随语言数增长。
- **已有约束须一并遵守**：语言知识零进代码（AGENTS 硬约束）、不留兼容垫片、
  删除先证后删（`policy/doc-alignment.md`）；配置加载 fail-fast。
- **预期待定**：属架构决策，动手前先立 ADR（`docs/decisions/`）；现仅记方向与命中点。
- **成熟解法参照（避免自造）**：
  - **GCC 的路线**：语言差异由**手写前端**接住（每个语言一个 front end），共享点在下游
    （GENERIC/GIMPLE IR + 后端 + 目标描述 `.md`）。它的"占位"不在前端骨架，而在
    `LANG_HOOKS`/`TARGET_HOOKS` 回调与机器描述文件——**取舍位置与我们相反**（它把共享点
    下移，我们把共享点上移到前端骨架）。另外 GCC 的机器描述是"配置面膨胀"的成熟解法样本：
    它给配置面配了**领域语言 + 代码生成器/校验器**（`.md` → `genrecog`/`genoutput`/
    `genattrtab`）——可见**配置面本身需要工具链管理**，否则就是纯负担。参照它设计我们的
    TOML→生成器/校验器（`number_gen` 这类"schema + 编译器"在**有生成器**时不算错）。
  - **LLVM**：IR 作为普适中间层的样本（前端/优化/后端三段解耦）。
  - **语言工作台（Xtext/Rascal/MPS）**：元语言 + 生成，与"配置表达式 + 插件补特异"同路线。
  - ⚠ 记录纪律：本仓文档不写"超过 X / 比 X 强"这类**不可验证的比较断言**（AGENTS
    「不拉踩开源作者」+ 对外话术纪律）；可比的是**取舍位置与可审计性**，且要同时写明
    自己的短板（无优化深度、语言规模墙、语义分析浅、单语言选择模型）。

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
