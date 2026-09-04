# lexer — 词法（token 定义驱动扫描）

> 文本 → Token 流。token 类型/符号/字符串/注释/数字形态全由 `grammar/` TOML
> 声明（`base/_token.toml` + `[lexer]` 段），本包不硬编码语言知识。

| 文件 | 一句话 |
|------|--------|
| `main_lexer.py` | Lexer 主扫描器（token 定义驱动 + 行状态/缩进单位锁定） |
| `capture_runner.py` | 配置驱动原始文本捕获（注释/字符串/块标量 token） |
| `number_gen.py` | 数字形态声明（`[[number.based]]`）→ FSM 转移表 |
| `number_runner.py` | 配置驱动数字解析（唯一路径） |
| `pre_scan.py` | 轻量预扫描（顶层声明符号收集） |
| `lexer_utils.py` | TOML 配置加载与合并工具 |

> 入口：`Lexer.tokenize`；缩进相关（YAML）看 `[indent]` 配置与 `_indent_unit`。
