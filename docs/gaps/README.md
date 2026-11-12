# gaps/ — 缺口档案（Gap Files）

> 记录 tpc **当前仍成立**的能力边界/缺口（接受项 + 未闭环项）的详细说明。
> **只记本体**：现状陈述 + 关联条目——不记过程（立项、体检、复核、闭环流转；
> 历史在 git log + CHANGELOG）。待办本身在 TODO/ROADMAP 一行 + 链到本档。

## 定位：与相邻文档的分工

| 位置 | 承载 | 与 gaps/ 的区别 |
|------|------|----------------|
| `gaps/` | tpc 自己的**能力边界/缺口**现状（接受项 + 未闭环项） | 焦点 = "我们现状差什么、还缺什么" |
| `docs/references.md` | **外部项目事实/调研**（别人怎么做的调研 + 设计来源落档） | gaps 引用它做"参照来源"，不重复外部事实 |
| `decisions/` | **生效中的决策**（为什么这么定） | 决策完成即删、正文不引 ADR 作锚；本档不写决策骨架 |
| 机制文档 | 系统怎么拼（含功能缺口评估段） | 机制文档内"缺口 N"若独立成项 → 可摘出到本档 |

一句话：**references 回答"别人怎么做"，gaps 回答"我们现状差什么"，机制文档回答"现在怎么拼"**。

## 档案模板

```markdown
# Gap — <主题>（<关联 TODO/ROADMAP 条目，若有>）

- 状态：接受（设计选择/范围） | 未立项 | 未闭环（剩 N 项）
- 关联：<TODO/ROADMAP 条目；相关机制文档>
- 参照：docs/references.md <相关调研段>（外部事实源，可选）

## 边界是什么（或：缺口是什么）
当前仍成立的陈述（够详细，避免下个 session 重新考古）。
未闭环项附：为什么是缺口/影响面；接受项附：为什么接受。

## 成熟解法参照（见贤思齐，未闭环项适用）
外部工具怎么解决 → 借鉴点（🔥 直接借鉴 / 💡 启发 / 📌 路线观察）。

## 可实现性（未闭环项适用）
方案形态 + 依赖前置 + 验证路径（拆几步、每步可独立验证）。

## 不做 / 未做（否掉的方向；无则删本节）
方向 + 反证（复现命令或依据）+ 触发条件（什么情况下复议）。条目消失即删。

## 关联条目
- <TODO/ROADMAP 链接、机制文档、测试门禁>
```

## 更新纪律

- **条目消失（修好/不再成立）→ 直接删条目或整档**（历史在 git log + CHANGELOG），
  不写"已修复/已闭环"注记。已完成的一次性计划（阶段规划、交付叙述、实测教训）不留在档内。
- **数字要可复核**：档内引用计数/比值/行数时给复现命令或指向测试；无仓内复现入口的
  历史数字须标注口径（否则下轮无法判断是否过期）。
- **单档行数上限 200**（`tests/policy/test_planning_doc_budget.py`）：超限先删旧条目，
  不靠"下次记得删"。
- 登记：本目录文件被 `docs/README` 索引引用（check_doc_refs 防孤儿）；
  新增档案本表加一行，删除同步移除。

## 当前档案

| 档案 | 主题 |
|------|------|
| `gap-tpc-check-external-checker.md` | tpc-check 外部 checker 插件协议（接入 veryl/verible/slang + 自管场景；ROADMAP P2.6） |
| `gap-comment-string-span-consistency.md` | 注释/字符串跨度判定两套实现（词法捕获器 A 侧：块标量折叠/触发谓词未闭环；预处理器行级状态机 B 侧：字符串内定界符误判、注释后同行指令不识别，接受） |
| `gap-parser-backtracking.md` | parser 回溯成本与 atom 位置级 memo（块 2 收口：cJSON 57.6s→2.98s；atom memo + 规则级 FIRST 早拒） |
| `gap-parser-linter-approximation.md` | parser/linter 错误处理近似（无恢复 + 启发式） |
| `gap-formatter-line-behavior.md` | formatter 行行为边界（宽度折行/保留行/对齐/幂等） |
| `gap-language-pack-scope.md` | 语言包范围与 yaml 边界（规模/SV/增强语法）+ C 包接受域现状 / 渲染保真现状 / `enabled` 档位边界 |
| `gap-language-penetration.md` | 语言知识渗透（引擎里实现了语言语义；词法/结构面实测快照 + 三条判据） |
| `gap-semantic-elaboration-boundaries.md` | 语义/插件契约（elaboration/单例/inject） |
| `gap-semantic-performance.md` | 语义层性能（check 耗时结构 2026-11-12 实测：elaborate 42–61% / parse 23–39%；端口源 per-port 全树扫描、41k 次渲染、树遍历热点；0.1.5 候选方向与 PyO3 暂缓判据） |
| `gap-c-semantic-base.md` | C 语义基座（符号表/作用域/声明顺序：`(myint)x` 截断丢内容、`myint *b;` 不可分、`sizeof` 宽进、引擎语义钩子空转；落点三案 + parser 接口四选一 + 待拍板 8 条） |
| `gap-c-preprocessor-scope.md` | C 预处理器范围基线（标准宏与指令全集三表 + 扩展排除表 + tpc 承载面与 4 处机制级缺口 + 首片 A/B；作者 2026-10-17 定"只考虑 C 标准中的宏"） |
| `gap-preprocessor-macro-timeline.md` | 预处理器宏展开时序（T1）：宏定义前/`#undef`/include 内定义顺序；两复现形态、事件表/终表机制缺口、A1 host 时序 + A2 include 预展开方案与判据/止损 |
| `gap-c-typedef-cast.md` | C typedef 名强转（G4）：解析前符号判定的调查与方案（最小矩阵/真实语料实测、M1/站点/符号来源三类缺口、B=parser 内符号表推荐 / A=raw 过渡 / C·D 否；待作者拍板引擎契约扩展） |
| `gap-c-real-corpus.md` | C 真实语料接入与误报基线（#43 调查轮：候选语料/许可、harness 前置、实测误报面、两类 linter FP 最小复现、方案 A/B/C 与门禁判据草案） |
| `gap-verification-engineering.md` | 验证与工程边界（sample-driven/吞吐/增量/覆盖） |
| `gap-engine-abstraction-audit.md` | 引擎能力面抽象审查（能力×语言矩阵 + 第二语言复用判据；刻度 7→9 完成后执行，日常循环顺带补行） |
| `gap-fragment-mode.md` | 片段模式 P0（记号模式 / island rewrite 原型：显式记号、bytes identity、死分支/假记号 fail-closed；P1 声明面/能力位待批准） |
| `gap-unit-graph.md` | unit graph 内置化（块 5 已实现：多入口多根森林 + `check` 多入参 + `--json` 图出口；边 kind = 语言包词汇（`[[unit_graph.edges]]`，能力 `unit_graph.edges.v2`）；P2 自动推 roots 留档） |
| `gap-incremental-parse.md` | 增量解析（块 7 P1 最小前置：同文件**单顶层单元**重解析 + 保守回退 + 编辑器接口；跨文件语义传播/常驻 watch 归 v0.2 P3.4） |
| `gap-feature-scatter.md` | 功能散点与上游契约耦合（一处功能 N 处登记；P-A/P-B/P-C + 步 2 收敛目标与接受边界） |
