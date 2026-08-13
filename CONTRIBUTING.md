# Contributing — 贡献指南

## 项目概览

TransParadigm Compiler (tpc) — 配置驱动的编译器前端。语言知识（token/语法/运算符/
渲染布局）全部外置在 `grammar/<lang>/` 的 TOML 声明中，引擎（core/lexer/parser/
analyzer/transform/renderer/linter）语言无关。c4 与 Verilog 是语言无关性的两个实证。

## 环境准备

```powershell
# 开发安装（editable + test 依赖）
pip install -e ".[test]"

# 跑全量测试（含覆盖率门禁 ≥84%）
python -m pytest tests -q --cov
```

## 目录结构

```
core/        语言无关引擎（规则注册/配置/插件加载）
lexer/       词法（token 配置驱动 + 数字形态生成器）
parser/      语法（规则加载/消歧/注入）
analyzer/    语义（作用域/符号/原语）
transform/   AST 变换（原语注册 + 插件）
renderer/    Doc IR + 布局算法 + 原语
linter/      前置语法检查（发现器/切片/多路径诊断）
preprocessor/宏/条件编译（primitive + 展开/还原）
grammar/     语言包（verilog / c4）+ 插件（typed_ports/formatter/...）
tests/       测试（引擎层/语言层/e2e）
docs/        设计文档（见下方索引）
```

## 开发约定

1. **不编码语言知识**：引擎层不写死任何 token 名/规则名/结构类别。语言知识一律
   TOML 声明 + 规则推导。改引擎前先自检：是否可用配置/字段替代？
2. **先补测试再改代码**：每个功能改动带测试；修复 bug 先写失败用例再修。
3. **TODO 只列未完成待办**：完成历史看 git log + 测试套件，不在 TODO 记完成状态。
4. **提交信息**：`[feature] 描述` 前缀 + 改动要点 + 验证结果（测试数/覆盖率）。

## 文档索引

| 文档 | 内容 |
|---|---|
| docs/language_walkthrough.md | 从零搭语言逐层指南（以 c4 为实例） |
| docs/config_lifecycle.md | 配置生命周期（declare_cfg 时序/坑） |
| docs/expression_conventions.md | 表达式隐式约定（Pratt/优先级） |
| docs/component_protocol.md | 插件层协议（组件/槽位/原语） |
| docs/grammar_rule_fields.md | 语法规则字段说明 |
| docs/coding_style.md | 代码风格 |
| docs/decisions/ | ADR（架构决策记录） |

## 测试规范

- 新功能：对应 `tests/<模块>/` 下新增测试文件。
- 语言包改动：跑 `pytest tests -q --cov` 确认门禁（≥84%）。
- e2e：`tests/e2e/`（管线/宏还原/保真度/增强渲染）。
- 幂等性：formatter 改动必须过 `tests/formatter/test_idempotent.py`。
