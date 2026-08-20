# Docs 导航

> 文档分层：**decisions/（为什么）→ architecture/（怎么拼）→ references/（是什么）**。
> 模型/人维护前，先查 `MODEL_INDEX.md` 跳转表定位，再读对应条目。
> ⚠ 分层只适用于**协作方文档**；个人思考沉淀不在其列，见下方"读者维度"。

## 结构

| 目录 | 读者 | 内容 |
|------|------|------|
| `decisions/` | 协作方（改造者+模型） | 为什么这么定（ADR，讨论痕迹沉淀） |
| `architecture/` | 协作方 | 系统怎么拼起来 |
| `references/` | 分两类（见读者维度） | 事实参考 / 设计来源记录 |
| 根目录文档 | 混合 | 各子系统架构说明（现有 .md 暂留原处，逐步归位） |

## 读者维度

文档读者分三类，决定它**是否进入对齐体系**（MODEL_INDEX / `Doc:` / `Impl:`）：

- **协作方（改造者 + 模型）** → 进对齐体系，是知识单元：`decisions/`、`architecture/`
- **作者本人（个人思考沉淀）** → 不进对齐体系
- **工具书参考**（配置字段/IEEE 标准）→ 按需引用，不强制对齐

> **原则：对齐工程化只服务于协作方文档；个人思考沉淀不套对齐约定**
> ——避免把文档体系本身变成新的维护负担。

## 当前文档索引

- 架构：`linter_architecture.md`（linter 两阶段发现+扁平检查）
- 决策：`decisions/0001-pre-parse-linter.md`、`decisions/0002-is-statement-explicit.md`、`decisions/0003-config-load-fail-fast.md`
- 参考：`config_reference.md`、`grammar_rule_fields.md`、`ieee1364_2005_annex_a.md`
- 教程：`language_walkthrough.md`（从零搭一门语言，以 c4 为实例——外部贡献者/模型上手参考）
- 机制：`config_lifecycle.md`（配置生命周期）、`expression_conventions.md`（表达式约定）、
  `component_protocol.md`（组件协议）、`api.md`（API 参考）、`coding_style.md`（代码风格）、
  `layout_spacing_prompt.md`（renderer layout DSL 原语与空格规则）
- e2e 样本参考：`e2e_real_projects.md`（real 组测试项目与语法面覆盖）
- 设计来源：`references.md`（参考项目 → 借鉴点，与 CREDITS.md 互补）

> **一次性计划文档**（评估/清理/改进计划）执行完后删除，成果记入 CHANGELOG——
> 避免 docs/ 堆积"已完成"的计划文档。

## 注释对齐约定（文档 ↔ 代码双向定位）

目的：模型维护时**直接跳转**到实现/验证位置，不做模糊搜索。

### 1. 代码 → 文档（`Doc:`）

每个模块文件头 docstring 末行声明对应文档条目：

```python
"""
scanner.py — 两阶段 Linter 编排器。

Doc: docs/linter_architecture.md   # 文件级引用（稳定，不随章节锚点漂移）
"""
```

### 2. 文档 → 代码（`Impl:` / `Test:`）

文档关键章节/ADR 条目声明实现与验证位置，精确到符号：

```markdown
> Impl: linter/scanner.py::LinterScanner.scan
> Test: tests/test_linter_discovery.py
```

### 3. 跳转表（`MODEL_INDEX.md`）

所有对齐条目的汇总表——模型改造前的第一站。新增对齐时同步更新该表。

### 维护规则

- **新增知识单元**（新模块/新决策/新机制）：三处同步——文件头 `Doc:`、文档 `Impl:`、`MODEL_INDEX.md` 一行。
- 引用的是"知识单元"级对齐（模块/关键符号），**不是每行注释**——避免成为新的维护负担。
- 符号重命名后更新 `Impl:` 与 `MODEL_INDEX.md`（grep `::` 可全量核对）。
