# API 参考

> 本文档列出核心模块的公共接口。完整 API 以源码 docstring 为准。

## CLI

```
tpc format <file>         格式化 Verilog 文件（全管线）
tpc lint <file> [--json]  语法检查（LSP 兼容 JSON）
tpc check <file> [--include DIR]  跨文件语义检查（语法 → 语义两阶段）
tpc pipeline [test]       跑单测（开发用）
tpc new component <name>  脚手架新组件
```

## 管线（pipeline 包）

```python
from pipeline import run_pipeline_on_source

result = run_pipeline_on_source(
    source=src,
    expand_macros=True,
    format_output=True,       # formatter 开关（默认 True）
    expand_enhanced=True,     # 增强语法展开/保留（默认 True 展开）
    schedule="default",       # 编排调度（ADR-0007）：命名 pass 序列
)
# result["output"] / result["success"] / result["idempotent"]
```

## 核心引擎

| 模块 | 接口 | 说明 |
|---|---|---|
| core.config_registry | `ConfigRegistry.load_all(rules_dir, ext_dirs, plugins_dir)` / `get(key)` / `declare_cfg(key, default, module, var)` | 声明式配置 |
| core.plugin_loader | `load_all_components(plugins_dir)` / `register_transform_slot(name)` / `get_transform_slots()` | 组件加载 |
| core.define | `Node` / `GrammarRule` / `Token` / `ParseError` / `GrammarRulesRegister` | 核心数据结构 |
| lexer | `Lexer(rules_dir)` / `.tokenize(text) -> list[Token]` | 词法 |
| parser | `Parser(rules_dir, rules, rule_selector)` / `setup_grammar(rules_dir, register, ext_dirs)` | 语法 |
| analyzer | `AnalysisTraversal(rules)` / `.analyze(ast)` | 语义 |
| transform | `AstTransformer()` / `AstTransformer.set_shared(key, val)` / `normalize_ast(ast)` | 变换 |
| pipeline | `run_pipeline_on_source(source, **kw)` / `format_generated(...)` | 管线入口（阶段编排 + 编排调度 ADR-0007；编排器在 `pipeline/schedule.py`） |
| renderer | `Renderer(rules_dir)` / `.render(node) -> str` | 渲染 |
| linter | `LinterScanner(rules_dir)` / `.scan(source) -> list[LintDiagnostic]` / `lsp_diagnostic(d)` | 检查 |
| preprocessor | `scan_directives(...)` / `expand_tokens(...)` / `restore_condition_blocks(...)` | 宏/条件编译 |

## Formatter 插件（grammar/verilog/plugins/formatter）

```python
from grammar.verilog.plugins.formatter import format_source
from core.define import DEFAULT_RULES_DIR

formatted = format_source(src, DEFAULT_RULES_DIR)
```

- pass 编排：indent → 品类对齐 → inst_port → wrap（build_engine）
- 风格配置：`[formatter.style]` indent_width / max_line_width
- 品类配置：`[[formatter.categories]]` matcher/family/break_distance

## 数字形态（P2.1 配置驱动）

```python
from lexer.number_gen import compile_patterns
from lexer.number_runner import ConfigNumberRunner
```

- 语言包声明 `[[number.based]]`（size/base_prefix/bases/value_digits/value_allow）
- 生成器编译为 FSM 转移表，lexer 按语言包接入

## 配置项速查（config/tpc_config.json）

> 作用：提供**项目级默认参数**，运行时可从控制台（CLI）显式覆盖。
> `run_pipeline_on_source` 的 `None` 参数会回落到这里的 pipeline 段。
> 定位顺序（core/_user_config.py）：`$TPC_CONFIG` 显式 > CWD 向上
> `config/tpc_config.json`（工作区隔离）> `~/.tpc/config.json`（全局 profile）> 内建默认。

```json
{
  "grammar": "grammar/verilog",
  "pipeline": {
    "stage": null,
    "out_dir": null,
    "analyzer": true, "transform": true, "renderer": true, "lint": true,
    "expand_macros": false,
    "format_output": true, "check_idempotent": true, "quiet": false,
    "include_dirs": [], "define": {}, "undefine": []
  }
}
```
