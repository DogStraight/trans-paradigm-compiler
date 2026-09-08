# API 参考

> tpc 公共接口导航。**完整签名以各模块 docstring 为准**——本文件不抄签名表
> （手写签名会与代码漂移；Go/CPython 生态只信 docstring 或自动生成）。
> 想调用 tpc 的某能力：从下表找入口模块 → 读该模块 docstring / 就近文档。

## CLI

```
tpc format <file>         格式化 Verilog 文件（全管线）
tpc lint <file> [--json]  语法检查（LSP 兼容 JSON）
tpc check <file> [--include DIR]  跨文件语义检查（语法 → 语义两阶段）
tpc pipeline [test]       跑单测（开发用）
tpc new component <name>  脚手架新组件
tpc config dump           显示配置 key 来源（调试）
```

命令定义在语言包 `tpc.toml [commands]`（声明差异项，未声明取全管线默认）；
用法/参数以 `main.py` docstring（CLI 权威）为准。

## 管线调用（pipeline 包）

```python
from pipeline import run_pipeline_on_source

result = run_pipeline_on_source(
    source=src,
    expand_macros=True,
    format_output=True,       # formatter 开关（默认 True）
    expand_enhanced=True,     # 增强语法展开/保留（默认 True 展开）
    schedule="default",       # 编排调度（见 pipeline/schedule.py + pipeline_stages.md）：命名 pass 序列
)
# result["output"] / result["success"] / result["idempotent"]
```

完整参数/返回值见 `pipeline/__init__.py` docstring；阶段顺序/数据形态见
`docs/engine_overview.md`（引擎一条线）。

## 引擎公共入口一览（stage-level components）

| 模块 | 公共入口 | 说明 |
|---|---|---|
| core.config_registry | `ConfigRegistry.load_all` / `ConfigRegistry.get` / `declare_cfg` | 声明式配置 |
| core.plugin_loader | `load_all_components` / `register_transform_slot` / `get_transform_slots` | 组件加载 |
| core.define | `Node` / `GrammarRule` / `Token` / `ParseError` / `GrammarRulesRegister` | 核心数据结构 |
| lexer | `Lexer` / `.tokenize` | 词法 |
| parser | `Parser` / `setup_grammar` | 语法 |
| analyzer | `AnalysisTraversal` / `.analyze` | 语义 |
| transform | `AstTransformer` / `.set_shared` / `normalize_ast` | 变换 |
| pipeline | `run_pipeline_on_source` | 管线编排入口（编排器 `pipeline/schedule.py`） |
| renderer | `Renderer` / `.render` | 渲染 |
| linter | `LinterScanner` / `.scan` / `lsp_diagnostic` | 前置 token 级 lint |
| preprocessor | `scan_directives` / `expand_tokens` / `restore_condition_blocks` | 宏/条件编译 |

## 就近详述的接口（本文件不重复）

- Formatter 插件（世界 B pass 管线、风格/品类配置）→
  `grammar/verilog/plugins/formatter/README.md`
- 数字形态（`[[number.based]]` → FSM，number_gen/number_runner）→
  `docs/language_walkthrough.md`（数字字面量 DFA）
- 用户配置（config/tpc_config.json 结构 + 定位顺序）→
  `core/config_lifecycle.md`
