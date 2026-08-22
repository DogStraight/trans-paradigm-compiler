# TransParadigm (tpc) — 项目导览

配置驱动的语言流水线：语言规则写在 TOML（`grammar/`）里，引擎是通用骨架。
当前实例语言：Verilog（`grammar/verilog/`）与 c4（`grammar/c4/`，从零搭出的示例语言）。

## 改任何子系统前

1. 先查 `docs/MODEL_INDEX.md` 跳转表：知识单元 → 文档位置 → 实现（Impl）→ 验证（Test）
2. 读对应 `docs/decisions/`（为什么，ADR）与架构文档（怎么拼）
3. 改代码时维护文件头 `Doc:` 反向引用（约定见 `docs/README.md`）
4. 跑对应测试（`tests/`）；改 linter 用 `tests/e2e/eval_lint_accuracy.py` 验证 recall/误报

## 硬约束

- **语言知识不进代码**：规则名、token 类型、结构名、表达式形态一律由
  `grammar/` TOML 配置、规则字段、推导提供，引擎不得硬编码任何语言具体知识。
- **配置加载 fail-fast**（`decisions/0003`）：配置错误直接报错，不静默降级。
- 文档分层只对协作方文档生效（decisions/architecture 进 MODEL_INDEX）；
  个人思考沉淀（`references.md` 等）不对齐，别给它套对齐约定。

## 子系统一句话

| 目录 | 职责 |
|------|------|
| `grammar/` | 语言规则（数据）：verilog/ 与 c4/ 的 TOML |
| `lexer/` | 词法：token 定义驱动的扫描 |
| `parser/` | 语法：递归下降 + Pratt + 规则选择 |
| `linter/` | 解析前的 token 级 lint（反解析器，复用同一 TOML 语法） |
| `preprocessor/` | 宏展开 / 反向映射 |
| `analyzer/` | 语义分析：作用域、符号、类型（primitives 扩展） |
| `transform/` | 语义映射 + 配置驱动变换 |
| `renderer/` | Doc IR → 格式化输出 |
| `core/` | 引擎骨架：配置注册、错误、插件加载 |

## 运行

- 入口：`main.py`（CLI）
- 测试：`pytest tests/`，零运行时依赖，无第三方包
