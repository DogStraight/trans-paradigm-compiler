# Docs 导航

> 文档分层：**decisions/（为什么）→ architecture/（怎么拼）→ references.md（外部调研/设计来源落档）**。
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
| `references.md` | 作者本人（见读者维度） | 外部调研/设计来源落档（不对齐；`references.md「章节」`被各处引用） |
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
- 决策：`decisions/README.md`（ADR 编号规则 + 模板 + 状态流；现存
  decisions/0003-0005/0007/0011 见 MODEL_INDEX 登记，已删 ADR 历史 git log）
- 参考：`references.md`（外部调研/设计来源落档：静态检查器功能调研见其「静态检查器功能调研」节）
  （语法规则字段参考已就近 `grammar/grammar_rule_fields.md`，见 grammar/README）
- 边界：已知边界完整清单 2026-09-04 按部件拆入 `gaps/`（见下"缺口档案"）；
  README 的 Known limitations 是其顶层摘要
- 教程：`language_walkthrough.md`（从零搭一门语言，以 c4 为实例——外部贡献者/模型上手参考）
- 机制：`config_lifecycle.md`（配置生命周期）、`component_protocol.md`（组件协议）
- 制度（该怎么做）：代码规约/发布 SOP/文档对齐约定已就近 `tools/policy/`
  （`tools/policy/coding-style.md` 代码风格 / `tools/policy/release-checklist.md`
  发布 SOP / `tools/policy/doc-alignment.md` Doc: 对齐约定——与门禁工具同层，
  见 tools/policy/README）
  （表达式书写约定已就近 `parser/expression_conventions.md`，见 parser/README）
  （renderer layout 空格纪律已就近 `renderer/layout_spacing_prompt.md`，见 renderer/README）
  （功能切面打包已就近 `packaging/packaging.md`，facets.json 规格随目录）
- 验证（fuzz/差分/边缘）：`tests/fuzz/README.md`（语法驱动 + 变异 fuzzing，不变量：不崩溃/token 保序/幂等）、`tests/edge/run_edge.py`（边缘语料门禁）、`tests/differential/run_differential.py`（与 verible-verilog-format 对拍，可选依赖）
- 缺口档案：`docs/gaps/README.md`（缺口文件规约 + 模板 + 分工）；
  `gaps/gap-tpc-check-external-checker.md`（试点：tpc-check 外部 checker 协议，ROADMAP P2.6）——
  每个缺口一个 `gaps/gap-*.md` 详细档案，宽泛条目在 TODO/ROADMAP 链过来
  （2026-09-04：原 known_limitations 边界按部件拆入 lexer/parser-linter/preprocessor/renderer-
  comment/formatter/language-pack/semantic/verification 8 聚合档，登记见 gaps/README）
- 地图/索引：各引擎子包目录 `README.md`（部件就近说明：每文件一句话，随目录同步）、
  `MODEL_INDEX.md`（知识单元跳转：文档 → 实现 → 验证，动手前查）
- 设计来源：`references.md`（参考项目 → 借鉴点，与 CREDITS.md 互补）

> **一次性计划文档**（评估/清理/改进计划）执行完后删除，成果记入 CHANGELOG——
> 避免 docs/ 堆积"已完成"的计划文档。

> 注释对齐约定（`Doc:`/`Impl:`/`Test:` + MODEL_INDEX 三处同步）2026-09-05
> 就近 `tools/policy/doc-alignment.md`（制度与门禁工具同层）；docs/README
> 只保留导航与分层说明。
