# Docs 导航

> 文档分层：**decisions/（为什么）→ architecture/（怎么拼）→ references/（是什么）**。
> 模型/人维护前，先查 `MODEL_INDEX.md` 跳转表定位，再读对应条目。
> ⚠ 分层只适用于**协作方文档**；个人思考沉淀不在其列，见下方"读者维度"。

> **描述性文本不就地停留 docs/**（2026-09-04 作者确立）：docs 不收"某物是什么 /
> 怎么用 / 清单"式描述——这类内容**就近放到承载其意义的文件旁**（实现 docstring /
> 就近子包 README / 插件目录 README，如 `checks/README.md`），docs 只留协作方
> 知识（decisions 为什么 / 架构怎么拼 / references 事实 / 规约 / 索引 / gaps）。
> 碰到 docs 描述性文本：**直接删，就近找承载**（对应 ADR-0011 A4 归属错→移动 /
> C2 漂移判据）。

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

- 架构：各子系统架构文档已就近子包（见下方注记；协作方"怎么拼"进 MODEL_INDEX）
  （linter 两阶段架构已就近 `linter/linter_architecture.md`，见 linter/README）
  （analyzer 语义检查插槽已就近 `analyzer/semantic_checks.md`，见 analyzer/README）
  （renderer 世界 A 架构已就近 `renderer/renderer_architecture.md`，见 renderer/README）
- 决策：`decisions/README.md`（ADR 编号规则 + 模板；0001-0008 各条见 MODEL_INDEX 登记）
- 参考：`references/static_checkers_survey.md`（静态检查器功能调研：Verilog/HDL 矩阵 + 规则引擎架构对比）
  （语法规则字段参考已就近 `grammar/grammar_rule_fields.md`，见 grammar/README）
- 边界：`known_limitations.md`（已知边界完整版——README 的 Known limitations 是其摘要）
- 教程：`language_walkthrough.md`（从零搭一门语言，以 c4 为实例——外部贡献者/模型上手参考）
- 机制：`config_lifecycle.md`（配置生命周期）、`component_protocol.md`（组件协议）
- 规约（该怎么做）：`coding_style.md`（代码风格：注释语言/分区标题/命名）
  （表达式书写约定已就近 `parser/expression_conventions.md`，见 parser/README）
  （renderer layout 空格纪律已就近 `renderer/layout_spacing_prompt.md`，见 renderer/README）
- 流程：`release_checklist.md`（发布 SOP：回归门禁 → 版本核对 → build → 包内容验证 → wheel 冒烟 → tag → PyPI 可选）
  （功能切面打包已就近 `packaging/packaging.md`，facets.json 规格随目录）
- 验证（fuzz/差分/边缘）：`tests/fuzz/README.md`（语法驱动 + 变异 fuzzing，不变量：不崩溃/token 保序/幂等）、`tests/edge/run_edge.py`（边缘语料门禁）、`tests/differential/run_differential.py`（与 verible-verilog-format 对拍，可选依赖）
- 缺口档案：`docs/gaps/README.md`（缺口文件规约 + 模板 + 分工）；
  `gaps/gap-tpc-check-external-checker.md`（试点：tpc-check 外部 checker 协议，ROADMAP P2.6）——
  每个缺口一个 `gaps/gap-*.md` 详细档案，宽泛条目在 TODO/ROADMAP 链过来
- 地图/索引：各引擎子包目录 `README.md`（部件就近说明：每文件一句话，随目录同步）、
  `MODEL_INDEX.md`（知识单元跳转：文档 → 实现 → 验证，动手前查）
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

Doc: linter/linter_architecture.md   # 文件级引用（稳定，不随章节锚点漂移）
"""
```

### 2. 文档 → 代码（`Impl:` / `Test:`）

文档关键章节/ADR 条目声明实现与验证位置，精确到符号：

```markdown
> Impl: linter/scanner.py::LinterScanner.scan
> Test: tests/engine/linter/test_linter_discovery.py
```

### 3. 跳转表（`MODEL_INDEX.md`）

所有对齐条目的汇总表——模型改造前的第一站。新增对齐时同步更新该表。

### 维护规则

- **新增知识单元**（新模块/新决策/新机制）：三处同步——文件头 `Doc:`、文档 `Impl:`、`MODEL_INDEX.md` 一行。
- 引用的是"知识单元"级对齐（模块/关键符号），**不是每行注释**——避免成为新的维护负担。
- 符号重命名后更新 `Impl:` 与 `MODEL_INDEX.md`（grep `::` 可全量核对）。
