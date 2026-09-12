# TransParadigm (tpc) — 项目导览

配置驱动的语言流水线：语言规则写在 TOML（`grammar/`）里，引擎是通用骨架。
当前实例语言：Verilog（`grammar/verilog/`）与 c4（`grammar/c4/`，从零搭出的示例语言）。

## 改任何子系统前

1. 先读 `docs/engine_overview.md`（引擎一条线，建立全景）再查 `docs/MODEL_INDEX.md`
   跳转表：知识单元 → 文档位置 → 实现（Impl）→ 验证（Test）
2. 读对应 `docs/decisions/`（为什么，ADR）与架构文档（怎么拼）
3. 改代码时维护文件头 `Doc:` 反向引用（约定见 `policy/doc-alignment.md`）
4. 跑对应测试（`tests/`）；改 linter 用 `tests/e2e/eval_lint_accuracy.py` 验证 recall/误报
5. 写代码守规约（非门禁软规约）：注释语言/分区标题/命名 →
   `policy/coding-style.md`；表达式书写约定 → `parser/expression_conventions.md`；
   **改过哪个 py 文件就清哪个文件的静态诊断** → `policy/pylance-cleanup.md`
   （agent 侧 Pylance MCP 逐文件查，清零判据见该文）

## 硬约束

- **语言知识不进代码**：规则名、token 类型、结构名、表达式形态一律由
  `grammar/` TOML 配置、规则字段、推导提供，引擎不得硬编码任何语言具体知识。
- **配置加载 fail-fast**（`core/config_lifecycle.md`）：配置错误直接报错，不静默降级。
- **不留向后兼容**：行为/配置/接口过时即删，不保留兼容垫片、deprecated 路径或
  "旧版分支"——历史在 git log 可追溯，删除优于兼容，避免死代码与双路径漂移。
  与 TODO"完成即删"同纪律：过时的直接删，而不是标记弃用后挂着。
- **删除先证后删**（判据全表见 `policy/doc-alignment.md`「删除判据」）：
  删除动作须命中
  判据——A 代码（A1 无引用 / A2 双实现 / A3 决策过时 / A4 归属错→移动 /
  A5 结构不一致）、B 注释（B1 零信息 / B2 与权威源重复 / B3 引已删目标 /
  B4 编辑残留 / B5 过时注记）、C 文档（C1 一次性完成 / C2 漂移 / C3 重复 /
  C4 版权）；说不出判据不删。反判据：调研/决策记录（references.md / ADR）、
  个人思考沉淀、CHANGELOG 历史——这些不是删除对象。
- 文档分层只对协作方文档生效（decisions/architecture 进 MODEL_INDEX）；
  个人思考沉淀（`references.md` 等）不对齐，别给它套对齐约定。

## 协作行为范式（后来 session 必须继承）

**克制推送：**
- 默认**只本地提交，不推送**。远程仓库是稳定的作品展示态，保持干净。
- 推送只在作者明确说"推"时执行；平时所有改动本地 `git commit` 攒着。
- 文档措辞保持中性工程化，不带"变现/领先/借鉴"这类指向性表述（公共历史里
  不留指向外部项目的显眼措辞）。

**见贤思齐：**
- **先看成熟解法，用已验证的模式**：遇到问题先调研成熟产品（Verilator/slang/
  Verible/SpyGlass/svlint 等）如何解决同一个问题，尽量采用已经验证的模式
  （机制、语义、边界处置），不闭门造车重新发明——这是见贤思齐的前置动作，
  先看再定要不要抄、怎么抄。
- 调研外部项目时，**不拉踩开源作者**：先讲对方做得好、值得学的地方；差异用
  "各有取舍，非优劣"表述，不用评分式/压人式语气。
- **文档放置速查（写/归档文档先判类；防污染与负重）**：
  - 决策（为什么）→ `docs/decisions/`（ADR），**≤10 决策点**：已完成删、
    长期 draft 方向注 ROADMAP 后删；删除前机制先落部件文档（历史 git log）。
  - 机制/架构（怎么拼）→ 就近引擎子包（`<pkg>/README.md` + 架构详述，如
    linter/linter_architecture.md、renderer/renderer_architecture.md、
    analyzer/semantic_checks.md）。
  - 描述性（是什么/怎么用/清单）→ **不就地 docs/**：就近 docstring / 子包
    README / 插件 README（layout/expression/grammar 字段已就地）；docs 只留
    协作方知识（为什么/怎么拼/制度/索引/gaps/教程）。
  - 制度（该怎么做/流程/约定）→ `policy/`（coding-style / release-checklist /
    doc-alignment，与门禁工具同层）。
  - 外部调研/设计来源 → `docs/references.md`——**只调研记录**（格式：定位 →
    管线对比 → 亮点 → 可实现性）；tpc 自身执行/落地/评测**不落**此。
  - 能力缺口/已知边界 → `docs/gaps/gap-*.md`（+ gaps/README 登记表）。
  - 执行记录/修复结果 → 代码 + 测试断言 + CHANGELOG（"为什么/推翻了什么"的
    结论层可留 ADR）。规则行为预期 → 测试断言，文档不重复。
  - 已删/过时内容 → git log 追，不留兼容垫片；删除先证后删（`decisions/0011`
    判据全表：A 代码/B 注释/C 文档）。
  - 讨论草稿/未成型中间产物 → `_drafts/`（根目录暂存区：**不进 git**、门禁
    排除；整理按上述分流落正式位后删原稿，不重复留档）。
- **先落档后动手**：调研/设计结论先按上述分流落档再立项实现，落档是动手的
  前置——不边做边定。
- 借鉴点标注层级：🔥 直接借鉴 / 💡 启发 / 📌 路线观察；"不实现"也要写明原因。
- **对拍验证**：成熟工具的输出可作 oracle（sv-parser 差分、format 对拍等），
  用已验证实现校验自己的行为——与"先看成熟解法"互补：一个抄机制，一个当裁判。

**实施节奏（分步分期）：**
- 大任务**分步分期**，每阶段可独立验证（测试/门禁通过才进下一阶段），
  不攒大改一次性提交；阶段完成即提交并汇报。
- **测试门禁 + 测后决策**：规则/改动过门禁（含真实语料实测量化误报）后
  按处置三选落地——修 / 降级 / 记录为已知边界；**回退只是处置之一，非
  必要**（过不了门禁才回退，结论照常落档）。
- **默认开/关是数据决策**：规则默认开关由实测误报面定——误报可接受就
  默认开（W 族先例），误报面大才默认关（NC/AW 先例），非固定策略。

**指令文件自身纪律（AGENTS.md 修剪）：**
- 与代码同纪律：某条范式 agent 无指令也稳定执行 → 删（"已能正确做就删"，
  调研来源见 references.md「知名 AGENTS.md 指令文件范式调研」），不靠堆
  指令改行为——删除谓词 = 该范式不再需要被提示（与不留向后兼容同构）。
- **不复制门禁**：测试门禁/工具已强制的项（lint 风格、hardcode gate、测试
  命令等）不写进 AGENTS.md——一行"由门禁强制，修它报的"胜过重复条目，
  省上下文预算（文件保持 ~100 行量级）。

**TODO/ROADMAP 维护纪律（两个文件都只留未完成）：**
- `TODO.md` 只列未完成待办，**完成项一律删除**（不保留 [x] 条目）——完成
  历史在 git log，决策记录在 references.md/ADR，TODO 不重复存。
- **短期待办在 `TODO.md`，中长期目标（backlog/非发布阻塞/v0.2 候选）在
  `ROADMAP.md`**；立项启动的项从 ROADMAP 移回 TODO，两文件同样完成即删。
  P 编号沿用原始编号（对应 git 历史与交叉引用），不重新编号。
- 每次"更新 TODO"动作必须**连带删除本次已闭环的条目**，不允许只加不减。
- **闭环即主动更新，无需作者提示**：每次任务收尾前主动同步 TODO/ROADMAP
  （删除本次闭环条目、立项项从 ROADMAP 移回 TODO），作为收尾固定环节，
  与代码改动一起本地提交。
- **调研/设计结论按"落档分流"落档**（见上），不进 TODO/ROADMAP——两文件里
  的注记只允许"指明待办方向的上下文"，不允许沉淀调研结论。

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
- 快速回归：`pytest -m smoke`（~12s，功能域代表层，日常改动先跑；分层见 `tests/README.md`）
- 全量测试：`pytest tests/`（零运行时依赖，无第三方包）
- 开发自查工具（都不进日常门禁，人工/按需跑）：
  - 增量覆盖率 `tools/check_coverage_delta.py`（只看改动文件，几十秒）
  - 真实语料误报基线 `tests/e2e/eval_diag_baseline.py`（增长即失败；查证误报用
    `eval_benchmark.py`，需外部 oracle）
  - 门禁有效性抽查 `tools/check_gate_efficacy.py`（真实事故变异，期望门禁变红）
