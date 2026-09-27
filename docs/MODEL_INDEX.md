# Model Jump Table（模型跳转索引）

> **模型/人维护任何子系统前，先查此表**——拿到"文档条目 → 实现位置 → 验证位置"的直接跳转，避免模糊搜索。
> 约定：文档条目写 `Impl:` 精确到符号；代码文件头写 `Doc:` 反向指向；新增对齐时同步本表。

## 使用方式

```
1. 你要改什么 → 在下方定位知识单元（或按子系统过滤）
2. 读对应"文档位置"（ADR/架构）理解为什么
3. 跳 `Impl:` 代码位置改
4. 跳 `Test:` 跑验证
```

> 先读 `engine_overview.md`（引擎一条线总览，建立全景）→ 再看部件全局轮廓：
> 各引擎子包目录 `README.md`（如 `parser/README.md`，就近描述每文件一句话，
> 随目录同步）；本表 = 任务导航（要改 X → 文档/实现/测试）。
> 三者分工：overview = 理解引擎怎么转（docs/）；就近 README = 部件目录内每
> 文件说明；本表 = 跨子系统任务跳转。
>
> **能力边界/接受项先查 `docs/gaps/README.md` 对应部件档案**：本表给"改哪里"，
> gaps 给"这算不算要改"（答案常是"刻意接受，非 bug"）。

## 跳转表（按子系统）

> 组织：主干条目（该子系统骨架，改前先读）→ 机制条目（特定功能/决策）。
> 横切机制（注释/文档治理/约定门禁）在「跨子系统」节；未立项设计在「待立项」节。
> 新增知识单元时按所属子系统插入对应节，并同步模块头 `Doc:`。

### parser — 语法（递归下降 + Pratt + 规则选择）

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| Parser 主引擎（递归下降 + 回溯，块/普通链调度） | `language_walkthrough.md`（Parser 主引擎：递归下降+回溯） | `parser/parser_core.py::Parser.parse`<br>`parser/_production.py`（生产式匹配主循环） | `tests/engine/parser/test_production_engine.py`<br>`tests/engine/parser/test_failure_report.py` |
| 块 & 语句级解析 | `language_walkthrough.md`（块规则解析） | `parser/block_parser.py` | `tests/engine/parser/test_production_engine.py` |
| 表达式解析（Pratt + 运算符优先级 + 注释挂载） | `language_walkthrough.md`（Pratt 表达式解析） | `parser/pratt_parser.py` | `tests/engine/parser/test_pratt_parser.py` |
| 规则选择（候选过滤 / 语句发现） | `language_walkthrough.md`（规则选择/语句发现） | `parser/rule_selector.py` | `tests/engine/parser/`（`test_production_engine.py` 等） |
| 规则形态分类 / FOLLOW 集派生 | `language_walkthrough.md`（规则形态分类） | `parser/follow.py` | `tests/engine/parser/test_follow.py` |
| node 绑定捕获（$N 绑定 + 路径提取） | `language_walkthrough.md`（node 绑定捕获） | `parser/attribute_binder.py` | `tests/engine/parser/test_attribute_binder.py` |
| EXT 注入（grammar inject：树层合并 + 传播 + 序列化） | `language_walkthrough.md`（EXT 注入）<br>`grammar/README.md`（注入归组：多条规则注入同一 target 须先归组容器） | `parser/grammar_inject.py`<br>`parser/rule_selector.py::serialize_production_tree` | `tests/engine/parser/test_grammar_inject.py`<br>`tests/engine/parser/test_production_serialize.py` |

### lexer — 词法（token 定义驱动扫描）

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| token 定义驱动扫描（主扫描器） | `language_walkthrough.md`（词法层：token 定义驱动） | `lexer/main_lexer.py::Lexer.tokenize` | `tests/engine/lexer/test_lexer.py` |
| 数字字面量 DFA（`[[number.based]]` 配置驱动） | `language_walkthrough.md`（数字字面量 DFA） | `lexer/number_gen.py`<br>`lexer/number_runner.py` | `tests/engine/lexer/test_number_gen.py`<br>`tests/engine/lexer/test_number_baseline.py` |
| 原始文本捕获（注释/字符串/块标量） | `language_walkthrough.md`（注释/字符串 token 扫描） | `lexer/capture_runner.py` | `tests/engine/lexer/test_capture_runner.py` |
| 注释形态读取（行注释起始 + 成对定界符，声明驱动） | `preprocessor/README.md`（marker 书写形态） | `lexer/comment_syntax.py::load_comment_syntax` | `tests/engine/lexer/test_comment_syntax.py` |
| 顶层声明预扫描 | `language_walkthrough.md`（预扫描：顶层声明收集） | `lexer/pre_scan.py` | `tests/engine/lexer/test_lexer.py` |
| 配置加载 fail-fast | `core/config_lifecycle.md` | `core/config_registry.py::ConfigRegistry.load_all`<br>`lexer/lexer_utils.py::merge_token_define` | `tests/engine/core/test_config_loading.py` |

### linter — 前置 token 级 lint（反解析器，复用同一 TOML 语法）

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 前置 token 级 linter（反解析器总述） | `linter/linter_architecture.md` | `linter/scanner.py::LinterScanner.scan`<br>`linter/discovery.py::Discovery.discover`<br>`linter/checkers/matcher.py::RuleMatcher` | `tests/engine/linter/test_linter_discovery.py`<br>`tests/engine/linter/test_linter_matcher.py`<br>`tests/e2e/eval_lint_accuracy.py` |
| Linter 两阶段架构（发现 + 扁平检查） | `linter/linter_architecture.md` | `linter/scanner.py`<br>`linter/checker.py::CheckerRegistry` | `tests/engine/linter/test_linter_checker.py` |
| is_statement 显式声明 | `linter/linter_architecture.md`（is_statement 显式标记） | `grammar/verilog/**/*.toml`（`is_statement = true`）<br>`core/define.py` | `tests/engine/linter/test_linter_lookahead.py` |
| 动态两级消歧（lookahead） | `linter/linter_architecture.md` | `linter/lookahead.py::LookaheadTable.classify` | `tests/engine/linter/test_linter_lookahead.py` |
| 语法切片（grammar_slicer） | `linter/linter_architecture.md` | `linter/grammar_slicer.py::build_slice_tree` | `tests/engine/linter/test_linter_slicer.py` |
| 表达式检查（pratt 复用） | `linter/linter_architecture.md` | `linter/checkers/expression.py` | `tests/engine/linter/test_linter_matcher.py` |
| 稳健性 / 畸形输入防御 | `linter/linter_architecture.md` | `linter/scanner.py::LinterScanner.scan` | `tests/engine/linter/test_linter_robustness.py` |
| 诊断位置精度（token_span） | `linter/linter_architecture.md` | `linter/__init__.py::token_span` | `tests/engine/linter/test_lint_accuracy.py` |
| 条件编译多路径诊断（diagnose） | `linter/linter_architecture.md` | `linter/diagnose.py` | `tests/engine/linter/test_diagnose.py` |
### analyzer — 语义分析（作用域/符号/类型 + 检查插槽）

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 作用域/符号模型 + 类型 | `analyzer/semantic_checks.md`（作用域/符号模型） | `analyzer/scope.py::Scope/Symbol`<br>`analyzer/context.py::AnalysisContext` | `tests/engine/analyzer/test_analyzer.py` |
| 遍历 + post-pass 钩子 | `analyzer/semantic_checks.md`（AnalysisTraversal + post-pass 钩子） | `analyzer/traversal.py::AnalysisTraversal` | `tests/engine/analyzer/test_analyzer.py`<br>`tests/engine/analyzer/test_diagnostic_related.py` |
| 语义检查插槽（post-pass 钩子 + related 链） | `analyzer/semantic_checks.md` | `analyzer/traversal.py::AnalysisTraversal._run_postpasses`<br>`analyzer/diagnostic.py::Diagnostic.related`<br>`core/plugin_loader.py::_load_postpasses` | `tests/engine/analyzer/test_diagnostic_related.py` |
| 声明式检查规则表（`[[checks]]` 规则=数据，P3/P4） | `analyzer/semantic_checks.md`（§3/§4/§9）<br>`references.md`（svlint 诊断链调研） | `core/check_registry.py`（加载/校验/用户配置）<br>`analyzer/checks.py`（kind 分发执行器）<br>`grammar/verilog/plugins/checks/name_check/`（NC001-NC011 + cases/ 样例 + `_filename_check.py` 跨文件 handler）<br>`tests/_check_test.py`（注释驱动测试） | `tests/languages/verilog/test_name_convention.py`（30 用例）<br>`tests/engine/analyzer/test_check_test.py`（19 用例） |
| 检查规则编写指南（L1 声明式 + L2 handler/postpass 双路径） | `grammar/verilog/plugins/checks/README.md`（双路径实操）<br>`analyzer/semantic_checks.md`（机制） | `grammar/verilog/plugins/checks/`（蓝本：name_check L1 / width_check postpass / inst_check 跨文件 / hier_check 服务型） | `tests/engine/analyzer/test_checker.py`<br>`tests/e2e/test_check_accuracy.py`（注释驱动门禁） |
| 跨文件语义检查（递归 + memo + 联动） | `analyzer/semantic_checks.md`（跨文件节） | `analyzer/checker.py::ProjectChecker`<br>`grammar/verilog/plugins/checks/inst_check/_inst_check.py`<br>`main.py::_cmd_check`（`tpc check`） | `tests/engine/analyzer/test_checker.py` |
| typed_ports 增强语法语义检查（TP 族，组件内 postpass + error 阻断展开） | `grammar/verilog/plugins/checks/README.md`（组件内检查登记）<br>`grammar/verilog/plugins/typed_ports/_check.py` docstring（为什么 + 三族检查点内联） | `grammar/verilog/plugins/typed_ports/_check.py::run_tp_check`（A 表述完整 TP001-004/006 / B 连接正确 TP010-012 / C 单驱动 TP020）<br>`grammar/verilog/plugins/typed_ports/tpc.toml`（postpass 挂载） | `tests/engine/analyzer/test_typed_ports_check.py`（18 用例）<br>`tests/e2e/samples/check_accuracy/cases/TP*`（pos/neg，expected.json focus） |
| 诊断 code 命名空间 + 豁免注释（tpc-check pylance 化） | `grammar/verilog/plugins/checks/README.md`（code 就近按插件索引）<br>`analyzer/suppress.py`（豁免语法 docstring）<br>`references.md`（Verilog 静态检查工具群调研） | `analyzer/suppress.py`（豁免过滤；注释标点取自 `lexer/comment_syntax.py`）<br>`analyzer/checker.py`（诊断序列化，LSP 兼容）<br>`main.py::_cmd_check`（--json + 豁免接入） | `tests/engine/analyzer/test_check_suppress.py`（17 用例，含 yaml 形态声明驱动） |
| **精化协议**（引擎只做文件操作；语言语义全归语言包精化项） | `core/component_protocol.md`（§1b 精化器能力位）<br>`analyzer/elaboration/README.md`（引擎侧职责 + 为什么这样切）<br>`grammar/verilog/plugins/elaboration/README.md`（插件侧五项 + 依赖通道） | `analyzer/elaboration/`（`contract` 契约与校验 / `driver` 驱动器 / `atoms` 原子供源 / `service` 语言无关服务句柄 / `loader` 能力读取点）<br>`grammar/verilog/plugins/elaboration/`（`_elaborator.py` 四项 + `_graph.py` 层 3） | `tests/engine/analyzer/test_elaborator_protocol.py`<br>`tests/engine/analyzer/test_elaboration_{param_default,port_decls,connections,gen_activity,signal_graph}.py`<br>`tests/engine/analyzer/test_elaborator_service.py`<br>`tools/min_pack_probe.py`（行为面回归护栏） |

### transform — AST 变换（配置驱动 + 插件）

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 变换引擎（AstTransformer + 插件自动注册） | `language_walkthrough.md`（变换引擎） | `transform/engine.py::AstTransformer` | `tests/engine/transform/test_comment_migrate.py` + `tests/languages/*`（c4_asm/typed_ports 集成） |
| 配置驱动变换 + 语义映射 | `transform/README.md`（语义映射机制：建表/resolved_ports 优先注入/消费；resolve_entries 已删）<br>`language_walkthrough.md`（端到端教程） | `transform/config_driven.py`<br>`transform/_semantic_mapping.py` | `tests/languages/verilog/test_typed_ports*.py`<br>`tests/languages/c4/test_c4_asm.py` |
| 结构保留规范化 | `language_walkthrough.md`（normalizer：结构保留规范化） | `transform/normalizer.py` | `tests/engine/parser/test_pratt_parser.py`（normalize 后断言）等 |

### renderer — Doc IR + 布局（世界 A）· 语言插件世界 B 见 grammar 节

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 世界 A 工作机制与现状（Doc IR + 原语 + 缺口评估；双世界关系见文） | `renderer/renderer_architecture.md` | `renderer/`（世界 A：Doc IR + 原语）<br>`grammar/verilog/plugins/formatter/`（世界 B：pass 管线，见其 README） | `tests/engine/renderer/`<br>`tests/languages/`<br>`tests/e2e/` |
| 渲染器改进路线（ADR-0006，六阶段落地；决策历史 git log） | `renderer/renderer_architecture.md`（缺口评估源自 ADR-0006） | `renderer/doc.py::layout`（内核扩展点）<br>`renderer/primitives/registry.py`（原语注册）<br>`renderer/node_renderer.py::render_node`（缩进上下文）<br>`grammar/verilog/plugins/formatter/`（世界 B） | `tests/engine/renderer/`（原语/缩进单测）<br>`tests/e2e/` + `tests/differential/`（门禁） |
| Doc IR（漂亮打印机中间表示）+ layout 布局 | `renderer/renderer_architecture.md` | `renderer/doc.py` | `tests/engine/renderer/test_renderer_doc.py` |
| 布局原语（registry + 各原语实现） | `renderer/renderer_architecture.md` | `renderer/primitives/` | `tests/engine/renderer/test_renderer_primitives.py`<br>`tests/engine/renderer/test_primitives_*.py` |
| renderer body 缩进（`body_cfg["indent"]`） | `language_walkthrough.md`（renderer：布局） | `renderer/node_renderer.py::_body_indent`<br>`renderer/node_renderer.py::render_node`（body 渲染段） | `tests/languages/yaml/test_yaml.py`<br>`tests/languages/c4/test_c4_asm.py`<br>`tests/e2e/test_real_fidelity.py` |
| 保真度分级（ADR-0006 阶段 5） | `renderer/renderer_architecture.md` | `renderer/fidelity.py` | `tests/engine/renderer/test_fidelity.py` |
| 注释槽位消费（leading/leading_own_line/trailing/inline/inline_after/LineSuffix） | `renderer/renderer_architecture.md`（注释处理节） | `renderer/node_renderer.py`（`_leading_slot_docs` 含直出文本节点路径） | `tests/engine/renderer/test_comment_slots.py` |

### preprocessor — 宏展开 / 反向映射

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 宏展开（strip 指令 + `` `NAME `` 引用展开） | `language_walkthrough.md`（预处理器） | `preprocessor/_expand.py` | `tests/engine/preprocessor/test_primitives.py` + `tests/languages/verilog/test_macro*.py` |
| 宏形态声明（`shape` 生产式 + 名字位候选列表；带参实参形态 `call_args` / `arg_separator`；后随字面量后缀 `suffix_after_call`） | `preprocessor/README.md`（形态清单） | `preprocessor/macro_shape.py`（声明解析 + 配平/切分 + 后缀编译）<br>`lexer/main_lexer.py::_match_macro_at`（词法落地） | `tests/engine/preprocessor/test_macro_shape.py`<br>`tests/engine/preprocessor/test_macro_call_args.py`<br>`tests/engine/preprocessor/test_macro_suffix.py` |
| 宏反向（统一位置桥：锚 + 原文回插） | `references.md`（语料前沿 M1：宏 inline+body 锚还原） | `preprocessor/_reverse.py`<br>`preprocessor/_bridge.py` | `tests/e2e/test_comment_restore.py` + 宏还原门禁 |
| 宏处置策略（引擎定义 mode 枚举；语言包以 `[capabilities] macro_policy` 声明策略） | `docs/decisions/0018-preprocessor-plugin-policy.md` + `preprocessor/README.md`（策略契约节） | `preprocessor/macro_policy.py`（取入口/校验）<br>`grammar/verilog/plugins/macro_policy/`（判定表） | `tests/engine/preprocessor/test_macro_policy.py` |
| tpc marker 通道（占位注释形态声明驱动 + 锚定位） | `preprocessor/README.md`（marker 书写形态） | `preprocessor/_markers.py`（书写/识别）<br>`preprocessor/_bridge.py::restore_anchors`（按锚回插） | `tests/engine/preprocessor/test_markers.py` |

### core + pipeline — 引擎骨架 / 配置 / 编排

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 配置加载 fail-fast | `core/config_lifecycle.md` | `core/config_registry.py::ConfigRegistry.load_all` | `tests/engine/core/test_config_loading.py` |
| 语言包↔引擎契约（`[engine] uses` 能力清单） | `core/config_lifecycle.md`（包↔引擎契约节） | `core/engine_compat.py`（协商）<br>`core/engine_capabilities.py`（能力表 + 推导）<br>`core/config_registry.py::_load_meta_declarations`<br>`core/define.py::_load_tpc_meta` | `tests/engine/core/test_engine_compat.py`（协商语义）<br>`tests/policy/test_engine_capabilities.py`（覆盖不变式） |
| 配置生命周期（注册 → 解析 → 消费） | `core/config_lifecycle.md`（§4b 声明级合并语义） | `core/config_registry.py`（`_resolve_decls` / `merge_by_name`） | `tests/engine/core/test_config_loading.py` |
| 启用组合（档位）覆盖参数 `enabled=` | `core/config_lifecycle.md`（§7 启用组合）<br>`grammar/c/README.md`（标准档位节）<br>`docs/gaps/gap-language-pack-scope.md`（运行时档位入口已落地） | `core/config_registry.py::{_tier_for_load,_tier_for_resolve,_ensure_entries_for}`<br>`core/config_registry.py::_resolve_cached`（key 含档位） | `tests/languages/c/test_c_standard_tiers.py`（26 构造 × 4 档矩阵）<br>`tools/check_gate_efficacy.py`（两条缓存键变异） |
| 组件协议 + 插件加载 | `core/component_protocol.md`（组件协议） | `core/plugin_loader.py`<br>`core/_protocol.py`（magic string 常量） | `tests/engine/core/test_plugin_cluster.py` |
| 插件回调能力化（P2.5：`[capabilities]`） | `core/component_protocol.md`（组件协议） | `core/plugin_loader.py::_load_capabilities`<br>`core/plugin_loader.py::get_capability`<br>`grammar/verilog/plugins/{typed_ports,formatter}/tpc.toml`（声明） | `tests/engine/core/test_capabilities.py`（9 用例） |
| 核心类型（Token/GrammarRule/Node） | `docs/README.md`（对齐约定） | `core/define.py` | `tests/engine/core/test_rule_schema.py` |
| Node 树通用工具（`iter_nodes` / `unwrap_optional` / `collect_nodes`） | `core/README.md`（define.py 行） | `core/define.py` | `tests/engine/analyzer/` + `tests/languages/`（经检查插件与 structure 间接覆盖） |
| 引擎约定机器化（check_hardcode 门禁） | `AGENTS.md`（硬约束：语言知识不进代码/路径规范/Doc 反向引用）<br>`docs/README.md`（Doc: 约定） | `policy/check_hardcode.py`（规则 1-4） | `tests/policy/test_check_hardcode.py`（17 用例） |
| 文档治理（调用点门禁 + 同步层 + 删除判据 + 引用纪律） | `policy/doc-alignment.md`（Doc: 约定 + 引用纪律 + 删除判据全表）<br>`docs/README.md`（导航索引） | `policy/check_doc_refs.py`（D1/D2 gate + D3/D4 info）<br>`policy/doc_sync.py`（refs/rename/delete 同步层） | `tests/policy/test_check_doc_refs.py`（24 用例）<br>`tests/policy/test_doc_sync.py`（15 用例） |
| 管线阶段契约（层间数据形态 + 阻断语义 + 跨阶段通道） | `pipeline_stages.md` | `pipeline/__init__.py::run_pipeline_on_source`（阶段编排）<br>各阶段 `_stage_*` | 全量 e2e（`tests/e2e/`）+ 注释 attachment 测试 |
| 分析/变换时点配置化 + 编排调度 | `docs/pipeline_stages.md`（编排调度节）<br>`pipeline/schedule.py`（机制自述 docstring） | `pipeline/schedule.py`（编排器一体：`build_schedules` + `_run_schedule` + `_run_pass_*`）<br>`core/plugin_loader.py::get_pipeline_pass_decls`（收集）<br>`pipeline/__init__.py`（按 rules_dir 缓存后注入） | `tests/engine/pipeline/test_schedule.py`（26 用例） |

### grammar 语言包与插件（语言知识 = 数据）

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 从零搭一门语言（教程，c4 实例） | `language_walkthrough.md` | `grammar/c4/**` | `tests/languages/c4/` |
| C 语言包（核心基线 ≈ C99 语法面 + c11/c17/c23 标准增量插件族） | `grammar/c/README.md`<br>`docs/gaps/gap-language-pack-scope.md`（分层草案 / C99 接受域清单 / 渲染保真现状） | `grammar/c/**` | `tests/languages/c/` |
| 语言包与插件目录约定 / 语法扩展工作流 | `language_walkthrough.md` | `grammar/{verilog,c,c4,yaml}/` + `plugins/` | `tests/languages/` |
| 渲染世界 B：Verilog formatter（pass 管线） | `grammar/verilog/plugins/formatter/README.md` | `grammar/verilog/plugins/formatter/` | `tests/languages/verilog/test_formatter*.py` |

### 跨子系统（横切机制）

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 注释节点模型（P1.5：注释 = AST 一等节点 + 槽位约定） | `renderer/renderer_architecture.md`（注释处理节）<br>`references.md`（Veryl CommentDoc/注释机制对照） | `renderer/node_renderer.py`（_comment_slots 槽位消费；`head_trailing` 经 `_insert_before_trailing_break` 插到 head 末尾换行点前）<br>`renderer/primitives/line.py`（inline_after 锚 token 定位）<br>`parser/_production.py`（行中注释挂载 + 行尾 trailing + 块头 trailing→head_trailing 迁槽）<br>`transform/engine.py::migrate_comments`（变换注释迁移） | `tests/engine/renderer/test_comment_slots.py`<br>`tests/engine/parser/test_comment_attachment.py`（含 `TestBlockEndTrailing` 逐行位置断言）<br>`tests/engine/transform/test_comment_migrate.py` |
| 注释单机制设计（源注释 = AST 节点元信息 + Comment 节点，普通注释锚点回插已删，tpc marker 独立通道；遗留边界 ①② 闭环） | `renderer/renderer_architecture.md`（注释处理节）<br>`references.md`（Veryl 对照） | 已实现（pratt op 间隙行中注释挂表达式节点 / 容器项间与首元素前独占注释 Comment 节点 / 块结束符与行尾 trailing / join 注释段与分隔符锚消费 / restore 纯 tpc） | `tests/e2e/test_comment_restore.py` + `test_comment_container.py`（门禁）<br>注释测试 4 文件（`test_comment_attachment`/`test_comment_slots`/`test_comment_migrate`/`test_pratt_comment_keep`） |

## 维护规则

- **新增知识单元**：在对应子系统节加一行 + 同步模块头 `Doc:`（三处对齐，见 docs/README）。
- 引用精确到符号（`file.py::Class.method`）；Test 指文件级（不加类/方法，防漂移）。
- 本表只做"指向权威源"的薄层——正文在文档位置列，不在此重复。
