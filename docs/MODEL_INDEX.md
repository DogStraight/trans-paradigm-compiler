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
| 前置 token 级 linter（反解析器） | `decisions/0001-pre-parse-linter.md` | `linter/scanner.py::LinterScanner.scan`<br>`linter/discovery.py::Discovery.discover`<br>`linter/checkers/matcher.py::RuleMatcher` | `tests/test_linter_discovery.py`<br>`tests/test_linter_matcher.py`<br>`verilog/eval_lint_accuracy.py` |
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
