# Docs 导航

> 文档分层：**decisions/（为什么）→ 就近机制文档（怎么拼）→ references.md（外部调研/设计来源落档）**。
> 模型/人维护前，先查 `MODEL_INDEX.md` 跳转表定位，再读对应条目。
> ⚠ 分层只适用于**协作方文档**；个人思考沉淀不在其列，见下方"读者维度"。

> **描述性文本不就地停留 docs/**（2026-09-04 作者确立）：docs 不收"某物是什么 /
> 怎么用 / 清单"式描述——这类内容**就近放到承载其意义的文件旁**（实现 docstring /
> 就近子包 README / 插件目录 README，如 `checks/README.md`），docs 只留协作方
> 知识（decisions 为什么 / 架构怎么拼 / references 事实 / 规约 / 索引 / gaps）。
> 碰到 docs 描述性文本：**直接删，就近找承载**（对应 `policy/doc-alignment.md`
> 「删除判据」的 A4 归属错→移动 / C2 漂移判据）。

## 结构

| 目录 | 读者 | 内容 |
|------|------|------|
| `decisions/` | 协作方（改造者+模型） | 为什么这么定（ADR；只在决策成立时建档，完成即删） |
| `references.md` | 作者本人（见读者维度） | 外部调研/设计来源落档（不对齐；`references.md「章节」`被各处引用） |
| 根目录文档 | 混合 | 引擎总览 / 管线阶段 / 教程 / 索引（机制文档已就近各子包） |

## 读者维度

文档读者分三类，决定它**是否进入对齐体系**（MODEL_INDEX / `Doc:` / `Impl:`）：

- **协作方（改造者 + 模型）** → 进对齐体系，是知识单元：`decisions/`、各子包
  机制文档（`<pkg>/README.md` + 架构文档）
- **作者本人（个人思考沉淀）** → 不进对齐体系
- **工具书参考**（配置字段/IEEE 标准）→ 按需引用，不强制对齐

> **原则：对齐工程化只服务于协作方文档；个人思考沉淀不套对齐约定**
> ——避免把文档体系本身变成新的维护负担。

## 当前文档索引

- 架构：各子系统架构文档已就近子包（见下方注记；协作方"怎么拼"进 MODEL_INDEX）
  （linter 两阶段架构已就近 `linter/linter_architecture.md`，见 linter/README）
  （analyzer 语义检查插槽已就近 `analyzer/semantic_checks.md`，见 analyzer/README）
  （renderer 世界 A 架构已就近 `renderer/renderer_architecture.md`，见 renderer/README）
  （引擎总览叙事 `engine_overview.md`：跨子系统一条线 + 全局骨架，改任何子系统前先读）
- 决策：`decisions/README.md`（入档纪律 + 编号 + 模板；完成即删——历史 git log，
  现存档由 `MODEL_INDEX.md` 指向的机制文档承载，不另设 ADR 清单）
- 参考：`references.md`（外部调研/设计来源落档：静态检查器功能调研见其「静态检查器功能调研」节）
  （语法规则字段参考已就近 `grammar/grammar_rule_fields.md`，见 grammar/README）
- 边界：`gaps/`（按部件的能力边界/缺口档案；只记当前仍成立的结论，过程/历史
  在 git log + CHANGELOG）；README 的 Known limitations 是其顶层摘要
- 教程：`language_walkthrough.md`（从零搭一门语言，以 c4 为实例——外部贡献者/模型上手参考）
- 机制：core 配置生命周期 + 组件协议已就近 `core/config_lifecycle.md`、
  `core/component_protocol.md`（见 core/README）
- 制度（该怎么做）：代码规约/发布 SOP/文档对齐约定已就近 `policy/`
  （`policy/coding-style.md` 代码风格 / `policy/release-checklist.md`
  发布 SOP / `policy/doc-alignment.md` Doc: 对齐约定——与门禁工具同层，
  见 policy/README）
  （表达式书写约定已就近 `parser/expression_conventions.md`，见 parser/README）
  （renderer layout 空格纪律已就近 `renderer/layout_spacing_prompt.md`，见 renderer/README）
  （功能切面打包已就近 `packaging/packaging.md`，facets.json 规格随目录）
- 验证（fuzz/差分/边缘）：`tests/fuzz/README.md`（语法驱动 + 变异 fuzzing，不变量：不崩溃/token 保序/幂等）、`tests/edge/run_edge.py`（边缘语料门禁）、`tests/differential/run_differential.py`（与 verible-verilog-format 对拍，可选依赖）
- 缺口档案：`docs/gaps/README.md`（档案规约 + 登记表）——能力边界/缺口一个
  `gaps/gap-*.md`，宽泛条目（TODO/ROADMAP）链接过来
- 地图/索引：各引擎子包目录 `README.md`（部件就近说明：每文件一句话，随目录同步）、
  `MODEL_INDEX.md`（知识单元跳转：文档 → 实现 → 验证，动手前查）
- 设计来源：`references.md`（参考项目 → 借鉴点）

> **一次性计划文档**（评估/清理/改进计划）执行完后删除，成果记入 CHANGELOG——
> 避免 docs/ 堆积"已完成"的计划文档。

## 放置速查（写/归档文档先判类；防污染与负重）

> 从 `AGENTS.md` 迁出（2026-09-18）；`AGENTS.md` 与 `policy/collaboration.md`
> 以本表为准，不再各存一份。

- **决策（为什么）** → `decisions/`（ADR），**≤10 决策点**：只在决策成立时建档、
  完成即删（未立项设计输入不进 ADR）；删除前机制先落部件文档（历史 git log）。
  现存流程型：`decisions/0022-engine-capability-audit.md`（刻度完成后的引擎能力面审查：
  方法/判据/台账位置；台账在 `gaps/gap-engine-abstraction-audit.md`）。
  案例型（决策 + 实现同轮落档）：`decisions/0023-tier-gated-grammar.md`（档位门控：
  可选件 grammar 随 `enabled` 加载；替代 ADR-0021 原"暂缓"行）。
- **长期暂缓项/触发条件（策略）** → `decisions/` 的**策略型 ADR**（"长期项不列待办" +
  「结论/为什么不做/触发条件」表，现存 `decisions/0021-long-term-deferral-strategy.md`）；
  **不进 TODO**——触发出现时按体量取回 TODO/ROADMAP，
  实现后删该 ADR 对应行（2026-10-17 定）。
- **机制/架构（怎么拼）** → 就近引擎子包（`<pkg>/README.md` + 架构详述，如
  `linter/linter_architecture.md`、`renderer/renderer_architecture.md`、
  `analyzer/semantic_checks.md`）。
- **描述性（是什么/怎么用/清单）** → **不就地 docs/**：就近 docstring / 子包
  README / 插件 README（layout/expression/grammar 字段已就地）；docs 只留协作方
  知识（为什么/怎么拼/制度/索引/gaps/教程）。
- **制度（该怎么做/流程/约定）** → `policy/`（coding-style / release-checklist /
  doc-alignment / collaboration，与门禁工具同层；清单见 `policy/README.md`）。
- **外部调研/设计来源** → `references.md`——**只调研记录**（格式：定位 →
  管线对比 → 亮点 → 可实现性）；tpc 自身执行/落地/评测**不落**此。
- **能力缺口/已知边界** → `gaps/gap-*.md`（+ `gaps/README.md` 登记表）。
- **主线进度刻度** → 根目录 `PROGRESS.md`（到下一个版本的剩余刻度 + 退出判据状态；
  只记状态不记过程，主线完成即整档删除或改写为下一主线）。
- **执行记录/修复结果** → 代码 + 测试断言 + CHANGELOG（"为什么/推翻了什么"的
  结论层可留 ADR）。规则行为预期 → 测试断言，文档不重复。
- **已删/过时内容** → git log 追，不留兼容垫片；删除先证后删（判据全表见
  `policy/doc-alignment.md`「删除判据」）。
- **讨论草稿/未成型中间产物** → 根目录 `_drafts/`（暂存区：**不进 git**、门禁
  排除；整理按上述分流落正式位后删原稿，不重复留档）。
- **预期外/未定判观察** → 根目录**短期草稿**（不常驻：有观察才建、每条必写"现象 +
  待判点 + 出口"、上限 8 条 / 70 行、**清空即删**；文件名与完整纪律见
  `policy/doc-alignment.md`「容量上限」——它不是第二个 TODO）。

> 注释对齐约定（`Doc:`/`Impl:`/`Test:` + MODEL_INDEX 三处同步）2026-09-05
> 就近 `policy/doc-alignment.md`（制度与门禁工具同层）；docs/README
> 只保留导航与分层说明。
>
> **规划文件容量纪律**（2026-10-08）：`TODO.md` / `ROADMAP.md` / `PROGRESS.md` /
> 根目录短期草稿 / `docs/gaps/gap-*.md` / `docs/decisions/NNNN-*.md` 都有行数上限，由
> `tests/policy/test_planning_doc_budget.py` 守——**超限先删旧条目或搬出现状边界**，
> 不靠"下次记得删"（口径见该测试 docstring）。
