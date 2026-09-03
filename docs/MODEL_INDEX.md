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

## 跳转表

| 知识单元 | 文档位置 | 实现位置（Impl） | 验证位置（Test） |
|----------|----------|------------------|------------------|
| 前置 token 级 linter（反解析器） | `decisions/0001-pre-parse-linter.md` | `linter/scanner.py::LinterScanner.scan`<br>`linter/discovery.py::Discovery.discover`<br>`linter/checkers/matcher.py::RuleMatcher` | `tests/engine/linter/test_linter_discovery.py`<br>`tests/engine/linter/test_linter_matcher.py`<br>`tests/e2e/eval_lint_accuracy.py` |
| is_statement 显式声明 | `decisions/0002-is-statement-explicit.md` | `grammar/verilog/**/*.toml`（`is_statement = true`）<br>`core/define.py` | `tests/engine/linter/test_linter_lookahead.py` |
| 配置加载 fail-fast | `decisions/0003-config-load-fail-fast.md` | `core/config_registry.py::ConfigRegistry.load_all`<br>`lexer/lexer_utils.py::get_token_define_merged` | `tests/engine/core/test_config_loading.py` |
| Linter 两阶段架构（发现+扁平检查） | `linter_architecture.md` | `linter/scanner.py`<br>`linter/checker.py::CheckerRegistry` | `tests/engine/linter/test_linter_checker.py` |

## 待补充（新增知识单元时在此登记）

| 知识单元 | 文档位置 | 实现位置 | 验证位置 |
|----------|----------|----------|----------|
| 动态两级消歧（lookahead） | `linter_architecture.md` | `linter/lookahead.py::LookaheadTable.classify` | `tests/engine/linter/test_linter_lookahead.py` |
| 语法切片（grammar_slicer） | `linter_architecture.md` | `linter/grammar_slicer.py::build_slice_tree` | `tests/engine/linter/test_linter_slicer.py` |
| 表达式检查（pratt 复用） | `linter_architecture.md` | `linter/checkers/expression.py` | `tests/engine/linter/test_linter_matcher.py` |
| 稳健性/畸形输入防御 | `linter_architecture.md` | `linter/scanner.py::LinterScanner.scan` | `tests/engine/linter/test_linter_robustness.py` |
| 诊断位置精度（token_span） | `linter_architecture.md` | `linter/__init__.py::token_span` | `tests/engine/linter/test_lint_accuracy.py` |
| 语义检查插槽（post-pass 钩子 + related 链） | `decisions/0004-semantic-check-slot.md`<br>`semantic_checks.md` | `analyzer/traversal.py::AnalysisTraversal._run_postpasses`<br>`analyzer/diagnostic.py::Diagnostic.related`<br>`core/plugin_loader.py::_load_postpasses` | `tests/engine/analyzer/test_diagnostic_related.py` |
| 声明式检查规则表（[[checks]] 规则=数据，P3/P4） | `semantic_checks.md`（§3/§4/§9）<br>`references.md`（svlint 诊断链调研） | `core/check_registry.py`（加载/校验/用户配置）<br>`analyzer/checks.py`（kind 分发执行器）<br>`grammar/verilog/plugins/checks/name_check/`（NC001-NC011 + cases/ 样例 + `_filename_check.py` 跨文件 handler）<br>`tests/_check_test.py`（注释驱动测试） | `tests/languages/verilog/test_name_convention.py`（30 用例）<br>`tests/engine/analyzer/test_check_test.py`（19 用例） |
| 检查规则编写指南（L1 声明式 + L2 handler/postpass 双路径） | `semantic_checks.md`（§11 实操指南 + 接口契约） | `grammar/verilog/plugins/checks/`（蓝本：name_check L1 / width_check postpass / inst_check 跨文件 / hier_check 服务型） | `tests/engine/analyzer/test_checker.py`<br>`.agents/skills/checker-rule-authoring/SKILL.md`（模型可加载指令包，随项目发布） |
| 插件回调能力化（P2.5：`[capabilities]` 能力注册协议） | `component_protocol.md`（组件协议） | `core/plugin_loader.py::_load_capabilities`<br>`core/plugin_loader.py::get_capability`<br>`grammar/verilog/plugins/{typed_ports,formatter}/tpc.toml`（声明）<br>`pipeline/__init__.py::format_generated` + `pipeline/schedule.py::_run_pass_analyze`（消费） | `tests/engine/core/test_capabilities.py`（9 用例） |
| 跨文件语义检查（递归+memo+联动） | `decisions/0005-cross-file-semantic-check.md` | `analyzer/checker.py::ProjectChecker`<br>`grammar/verilog/plugins/checks/inst_check/_inst_check.py`<br>`main.py::_cmd_check`（`tpc check`） | `tests/engine/analyzer/test_checker.py` |
| renderer body 缩进（`body_cfg["indent"]`） | `language_walkthrough.md`（renderer：布局） | `renderer/node_renderer.py::_body_indent`<br>`renderer/node_renderer.py::render_node`（body 渲染段） | `tests/languages/yaml/test_yaml.py`<br>`tests/languages/c4/test_c4_asm.py`<br>`tests/e2e/test_real_fidelity.py` |
| 渲染器改进路线（ADR-0006） | `decisions/0006-renderer-improve-roadmap.md` | `renderer/doc.py::layout`（内核扩展点）<br>`renderer/primitives/registry.py`（原语注册）<br>`renderer/node_renderer.py::render_node`（缩进上下文）<br>`grammar/verilog/plugins/formatter/`（世界 B） | `tests/engine/renderer/`（原语/缩进单测）<br>`tests/e2e/` + `tests/differential/`（门禁） |
| 渲染器工作机制与现状（双世界 + 缺口评估） | `renderer_architecture.md` | `renderer/`（世界 A：Doc IR + 原语）<br>`grammar/verilog/plugins/formatter/`（世界 B：pass 管线） | `tests/engine/renderer/`<br>`tests/languages/`<br>`tests/e2e/` |
| 引擎约定机器化（check_hardcode 门禁） | `AGENTS.md`（硬约束来源：语言知识不进代码/路径规范/Doc 反向引用）<br>`docs/README.md`（Doc: 约定） | `tools/policy/check_hardcode.py`（规则 1-4：token 字面量/grammar 路径/Doc 头/插件导入） | `tests/policy/test_check_hardcode.py`（17 用例，含真实仓库门禁回归） |
| 文档治理（调用点门禁 + 同步层 + 删除判据，ADR-0011） | `docs/README.md`（Doc: 约定 + 导航索引）<br>`decisions/0011-doc-governance.md`（设计 + 删除判据全表） | `tools/policy/check_doc_refs.py`（D1/D2 gate：Doc: 头 + 导航索引目标存在；D3/D4 info：Impl/Test 文件级 + 孤儿提醒）<br>`tools/policy/doc_sync.py`（refs/rename/delete 同步层） | `tests/policy/test_check_doc_refs.py`（24 用例）<br>`tests/policy/test_doc_sync.py`（15 用例，含真实仓库门禁回归） |
| 诊断 code 命名空间 + 豁免注释（tpc-check pylance 化） | `diagnostics.md`（code 清单 + suppress 语法）<br>`references.md`（Verilog 静态检查工具群调研） | `analyzer/suppress.py`（豁免过滤）<br>`analyzer/checker.py`（诊断序列化，LSP 兼容）<br>`main.py::_cmd_check`（--json + 豁免接入） | `tests/engine/analyzer/test_check_suppress.py`（13 用例） |
| 管线阶段契约（层间数据形态 + 阻断语义 + 跨阶段通道） | `pipeline_stages.md` | `pipeline/__init__.py::run_pipeline_on_source`（阶段编排）<br>各阶段 `_stage_*` | 全量 e2e（`tests/e2e/`）+ 注释 attachment 测试 |
| 分析/变换时点配置化 + 编排调度（ADR-0007） | `decisions/0007-pipeline-schedule.md` | `pipeline/schedule.py`（编排器一体：`build_schedules` 声明+序列器、`_run_schedule` 执行、`_run_pass_*` 执行器）<br>`core/plugin_loader.py::get_pipeline_pass_decls`（收集）<br>`pipeline/__init__.py`（按 rules_dir 缓存 schedules/mapping_cfg 后注入） | `tests/engine/pipeline/test_schedule.py`（26 用例） |
| 注释节点模型（P1.5：注释 = AST 一等节点 + 槽位约定） | `decisions/0006-renderer-improve-roadmap.md`（注释遍路线）<br>`references.md`（Veryl CommentDoc/注释机制对照 + 设计来源） | `renderer/node_renderer.py`（_comment_slots 槽位消费：leading/trailing/inline）<br>`renderer/primitives/line.py`（inline_after 锚 token 定位）<br>`parser/_production.py`（行中注释挂载 + 尾注 trailing）<br>`transform/engine.py::migrate_comments`（变换注释迁移，deep 收集）<br>`pipeline/__init__.py`（未消费 inline_after 兜底回插） | `tests/engine/renderer/test_comment_slots.py`（9 用例）<br>`tests/engine/parser/test_comment_attachment.py`<br>`tests/engine/transform/test_comment_migrate.py`（9 用例） |
| 注释单机制设计（ADR-0013：源注释 = AST 节点元信息 + Comment 节点，普通注释锚点回插通道已删除，tpc marker 独立通道） | `decisions/0013-comment-single-mechanism.md` | 已实现（pratt op 间隙行中注释挂表达式节点 / 容器项间与首元素前独占注释 Comment 节点 / 块结束符行尾 trailing / join 注释段与分隔符锚消费 / line+inline 普通回插删除，restore 纯 tpc） | `tests/e2e/test_comment_restore.py` + `test_comment_container.py`（容器/首元素前/块结束符注释门禁）<br>既有注释测试 4 文件（`test_comment_attachment`/`test_comment_slots`/`test_comment_migrate`/`test_pratt_comment_keep`） |
| 增量解析设计（P3.1-P3.6 共同输入，ADR-0009 draft） | `decisions/0009-incremental-parse-design.md` | 待实现（P3 立项后；双向映射/结构锚定/merge 校验/缓存选址设计见 ADR） | ROADMAP P3.1-P3.6（立项后补测试） |
| C 语言包前置研判（注入vs替换 + 用户标定打包，ADR-0010 draft） | `decisions/0010-c-langpack-prerequisites.md` | 待实现（C 语言包/多语言分发立项后；`[inject]` mode 声明面 + `[packaging]` 段设计见 ADR） | ROADMAP C 语言包 / 用户标定打包条目（立项后补测试） |
| 多后端输出设计（P4.1 蓝图，ADR-0012 draft） | `decisions/0012-multibackend-output.md` | 待实现（P4 立项后；Renderer.layout_dirs + plugin_loader target 识别设计见 ADR） | ROADMAP P4.1（立项后补测试） |
