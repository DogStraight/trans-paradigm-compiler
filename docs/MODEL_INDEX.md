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
| 前置 token 级 linter（反解析器） | `decisions/0001-pre-parse-linter.md` | `linter/scanner.py::LinterScanner.scan`<br>`linter/discovery.py::Discovery.discover`<br>`linter/checkers/matcher.py::RuleMatcher` | `tests/test_linter_discovery.py`<br>`tests/test_linter_matcher.py`<br>`tests/e2e/eval_lint_accuracy.py` |
| is_statement 显式声明 | `decisions/0002-is-statement-explicit.md` | `grammar/verilog/**/*.toml`（`is_statement = true`）<br>`core/define.py` | `tests/test_linter_lookahead.py` |
| 配置加载 fail-fast | `decisions/0003-config-load-fail-fast.md` | `core/config_registry.py::ConfigRegistry.load_all`<br>`lexer/lexer_utils.py::get_token_define_merged` | `tests/test_config_loading.py` |
| Linter 两阶段架构（发现+扁平检查） | `linter_architecture.md` | `linter/scanner.py`<br>`linter/checker.py::CheckerRegistry` | `tests/test_linter_checker.py` |

## 待补充（新增知识单元时在此登记）

| 知识单元 | 文档位置 | 实现位置 | 验证位置 |
|----------|----------|----------|----------|
| 动态两级消歧（lookahead） | `linter_architecture.md` | `linter/lookahead.py::LookaheadTable.classify` | `tests/test_linter_lookahead.py` |
| 语法切片（grammar_slicer） | `linter_architecture.md` | `linter/grammar_slicer.py::build_slice_tree` | `tests/test_linter_slicer.py` |
| 表达式检查（pratt 复用） | `linter_architecture.md` | `linter/checkers/expression.py` | `tests/test_linter_matcher.py` |
| 稳健性/畸形输入防御 | `linter_architecture.md` | `linter/scanner.py::LinterScanner.scan` | `tests/test_linter_robustness.py` |
| 诊断位置精度（token_span） | `linter_architecture.md` | `linter/__init__.py::token_span` | `tests/test_lint_accuracy.py` |
| 语义检查插槽（post-pass 钩子 + related 链） | `decisions/0004-semantic-check-slot.md`<br>`semantic_checks.md` | `analyzer/traversal.py::AnalysisTraversal._run_postpasses`<br>`analyzer/diagnostic.py::Diagnostic.related`<br>`core/plugin_loader.py::_load_postpasses` | `tests/engine/analyzer/test_diagnostic_related.py` |
| 跨文件语义检查（递归+memo+联动） | `decisions/0005-cross-file-semantic-check.md` | `analyzer/checker.py::ProjectChecker`<br>`grammar/verilog/plugins/inst_check/_inst_check.py`<br>`main.py::_cmd_check`（`tpc check`） | `tests/engine/analyzer/test_checker.py` |
| renderer body 缩进（`body_cfg["indent"]`） | `language_walkthrough.md`（renderer：布局） | `renderer/node_renderer.py::_body_indent`<br>`renderer/node_renderer.py::render_node`（body 渲染段） | `tests/languages/yaml/test_yaml.py`<br>`tests/languages/c4/test_c4_asm.py`<br>`tests/e2e/test_real_fidelity.py` |
| 渲染器改进路线（ADR-0006） | `decisions/0006-renderer-improve-roadmap.md` | `renderer/doc.py::layout`（内核扩展点）<br>`renderer/primitives/registry.py`（原语注册）<br>`renderer/node_renderer.py::render_node`（缩进上下文）<br>`grammar/verilog/plugins/formatter/`（世界 B） | `tests/engine/renderer/`（原语/缩进单测）<br>`tests/e2e/` + `tests/differential/`（门禁） |
| 渲染器工作机制与现状（双世界 + 缺口评估） | `renderer_architecture.md` | `renderer/`（世界 A：Doc IR + 原语）<br>`grammar/verilog/plugins/formatter/`（世界 B：pass 管线） | `tests/engine/renderer/`<br>`tests/languages/`<br>`tests/e2e/` |
| 引擎约定机器化（check_hardcode 门禁） | `AGENTS.md`（硬约束来源：语言知识不进代码/路径规范/Doc 反向引用）<br>`docs/README.md`（Doc: 约定） | `tools/policy/check_hardcode.py`（规则 1-4：token 字面量/grammar 路径/Doc 头/插件导入） | `tests/policy/test_check_hardcode.py`（17 用例，含真实仓库门禁回归） |
