# Gap — 片段模式 P0（记号模式 / island rewrite 原型）

- 状态：**P0 完成（#70，2026-10-23）**；**P1 已落地（2026-10-30，全域岛 / 零声明面）**：
  `islands/` 五模块 + `tpc fragment` 改走；P0 记号原型与 `tools/fragment_rewrite.py`
  已删除（无兼容垫片）。
- 实现：`islands/`（model/segment/process/splice/rewrite；CLI `tpc fragment`，dry-run diff；
  `--write` 落盘）；测试 `tests/engine/test_islands.py`。
- 设计输入：已内联到本档「P1 契约」「P2/P3 契约与退出判据」节（原讨论稿随收尾销毁，不复用草稿路径）。
- **调研输入（2026-10-30）**：`docs/references.md`「岛式分片 / 部分解析」——五档先例
  （岛式语法 / included ranges / 标记忽略 / 范围格式化 / 轻量结构改写）的共性提炼；
  以下三条已并入 P1 契约：**边界落在语法单元**、**岛内只走真实管线**、**后验默认开**。
- 关联：`PROGRESS.md` 块 3/4；`docs/decisions/0026-fragment-mode-islands.md`；`ROADMAP.md`「当前主线」；`docs/gaps/gap-parser-linter-approximation.md`（parser 无错误恢复为刻意接受，本工具不改 parser）。

## P0 契约（已实现）

- 记号：行注释 `// tpc:fragment id=<id> begin` … `// tpc:fragment end`（**单层**、显式 id；不复用内部 `<tpc:...>` marker 命名空间）。
- 规则：区域内 token 序列 `always @ ( * )` → `always @*`（纯语法、可逆、无 scope/类型/宏依赖）。
- 作用面：**raw 原文**（不展开宏、不建 AST、不依赖 analyzer/linter）。
- 编辑集从右向左拼接；无命中时**逐字节**返回原 bytes（BOM/CRLF/无尾换行保真）。
- fail-closed：未闭合/嵌套/错配、条件指令扫描失败、编辑重叠 ⇒ 不落任何编辑并报错。
- 死分支：`scan_directives` 的 condition_blocks `active=false` 分支行 = 水域，记号忽略；字符串/块注释里的假记号因非行注释 token 而忽略。

## 证据（#70）

| 判据 | 结果 |
|---|---|
| 单测（identity 四例/假记号/死分支/未闭合/嵌套/幂等/CLI dry-run+write） | **10 passed** |
| 真实文件（AW002_mixed_assign/top.sv，加记号圈全文件） | 1 处命中，0 误改；`always @(*)` 1→0、`always @*` 0→1；≈145ms |
| 真实语料 A/B（tests/e2e/samples 下 259 个 .v/.sv，无记号） | **0 文件变化、0 错误**（9.1s） |
| pyright / structural | 0 errors；S Δ0（`_parse_markers` 两项 P0 状态机登记 kept） |

**falsification 结论（P0 层面成立）**：纯语法、片段内可判定的改写可独立于全量 parse 完成；
identity/死分支/假记号/幂等四类安全判据可证；不触碰正式 grammar/parser 阻断语义。
**未证明**：隐式锚点命中率、多规则冲突/嵌套、真实工程采用需求——按草稿 P1/P2 再评估。

## P0 明确不做

- 不做隐式锚点（首 token/关键字预筛）；不做块注释/嵌套/无 id 记号；不做非 Verilog 规则；
- 不做 `expanded` 面映射回原文；不新增 `[[island_rules]]` 声明段、不新增能力位、不改默认管线。

## P1 契约（全域岛，作者 2026-10-30 最终确认）

**批复（两轮）**：① 对外名 `tpc fragment` 定稿；② **不建任何"岛声明"配置面**——不做
`[[island_rules]]`、不做 `island_rewriter` 能力位：**开片段模式后，默认接触到的语法都是
岛**（岛 = 语法配置推导出的语法单元）；③ 不做"改写规则集合"；④ 记号机制随之退役（P0 原型
淘汰，无兼容垫片）。

**为什么原稿有"规则集合/岛声明"**：P0 用手写 `always @(*)`→`always @*` 证明标记与安全
边界，P1 草稿沿用它、误当骨架。调研发现 linter 的语言无关推导层（`linter/discovery.py` 等，包内组件）已能从
语法 TOML 得出同样的分片信息（规则表 → 切片树 → FIRST → 前瞻 → 发现树），零语言字面量
⇒ 岛种类/边界/结束全部可推导，配置面零新增（依据作者 2026-10-30：「根本没有必要有 island，
开片段模式后，默认接触到的语法都是 island 了」）。

**分片模型**：

- 岛 = `linter.discovery.Discovery` 从 token 流产出的 `DiscoveredNode` 树节点（rule + token 区间
  + children）：块级节点含 body children，叶节点到语句级，两者都可当岛。
- water = 未被任何节点覆盖的 token / 未识别位点 / 含宏或指令行的区间（后两者不进管线，
  避免展开语义改动原文）；water 逐字节保留。
- **记号（`tpc:fragment`）退役**：P1 不再需要用户圈定区域；P0 记号配对/死分支判据随原型
  删除。P0 的安全不变量（字节 identity / fail-closed / 双跑幂等）保留，改为对"无岛/水区间"
  成立。
- 处理粒度 = **自顶向下**：节点文本进管线成功 ⇒ 整段替换、不再处理其子节点；失败 ⇒ 递归
  子节点；子节点也失败 ⇒ 该区间落水。这正是"能解析/能变换的部分进管线，其余原样"。
- 岛内一律走真实管线（parse+render；是否带 transform/check 由 CLI 管线开关决定，引擎不另
  造近似规则）；岛输出按插入位置**重定缩进基线**后替换原区间。

**边界与后验**：岛起止天然落在 token 边界（发现层推导）；管线失败 ⇒ 原样保留（fail-closed）；
无岛或零变化 ⇒ 逐字节返回原 bytes；后验**默认开启且无跳过开关**：岛级重解析 + 双跑幂等 +
字节 identity（P2 的 `--verify full` 只增加"全文件级"档，不是跳过手段）。

**P1 验收（2026-10-30 证据）**：
- 单测 `tests/engine/test_islands.py` 10 passed（identity/BOM+CRLF/岛处理/water 保留/
  宏落水/双跑幂等/C 包同机制）；
- 真实语料冒烟 12 文件：0 crash、0 non-idempotent、处理后再次改写逐字一致；
- `eval_lint_accuracy`：33 hit / 0 miss / 0 fp（linter 面未回归）；
- 默认行为不变：片段模式是独立命令，`format`/`lint` 等入口未改。

**P1 落地内容（2026-10-30）**：

1. ADR-0026（`docs/decisions/0026-fragment-mode-islands.md`）：全域岛 / 零声明面 / 后验。
2. `islands/`：`model.py`（复用 linter 推导组件）、`segment.py`（字符区间/water/缩进）、
   `process.py`（真实管线 + 重解析 + 双跑幂等）、`splice.py`（重定缩进基线 + 编辑集）、
   `rewrite.py`（自顶向下编排 + bytes identity）。
3. CLI：`tpc fragment` 改走 `islands/`；`tools/fragment_rewrite.py` 与 P0 记号测试删除。
4. 门禁：单测 10 条 + 真实语料冒烟 + `eval_lint_accuracy`；按「改哪跑哪」纪律未跑全量。

## 岛信息如何从语法配置推导（调研 2026-10-30）

**结论**：不需要在引擎里写任何语言字面量，也不需要为每个语言手写"岛类型清单"——
现有 linter 的**语言无关推导层**已经从语法配置得出同样的分片信息，可直接作为
islands 模块的数据源。

**现有设施的分工**（`优先看 linter`）：

| 层 | 位置 | 吃什么 | 产出 |
|---|---|---|---|
| 语法加载 | `parser/__init__.py::setup_grammar` | 语言包 TOML 规则 | `GrammarRule` 表（`is_block`/`is_statement` 为规则自声明；`block_start`/`block_end` 由 production 首尾字面 token 推导） |
| 切片树 | `linter/grammar_slicer.py::build_slice_tree` | 规则表 | `{rule: {prods, is_block, is_statement, block_start, block_end}}`（linter 内部推导组件，islands 直接消费） |
| FIRST 集 | `core/first_set.py::first_tokens`（linter 侧 re-export） | feature 树 | 每规则起始 token 集（保守/可空两种语义） |
| 前瞻分类 | `linter/lookahead.py::LookaheadTable` | 切片树 + 匹配器 | token → 候选规则（A 类 keyword_map / B 类标识符+前缀路径） |
| 结构发现 | `linter/discovery.py::Discovery` | 切片树 + 块/括号起止符 + `[discovery]` 声明 | **岛信息**：`DiscoveredNode(rule, start, end, children)` 树 + 未识别区间 |
| 语言事实声明 | `linter/discovery_shape.py` + `base/_discovery.toml` | 语言包 `[discovery]` 段 | 容器/延续/属性对/子句分隔符（语义意图，声明而非猜；ADR-0025） |

**实测（本机 probe）**：`module m(...); always @(*) begin ... end always @(...) begin : named ... end endmodule`
→ `ModuleDecl [0,57)`，children = 两个 `AlwaysStmt [15,28)` / `[29,55)`；未知构造
（`class C; endclass`）→ `unrecognized: 1`（岛外 = water）。全程零语言字面量。

**islands 模块设计（吃语法配置 → 分片信息）**：

```
islands/
  model.py     # 语法配置 → IslandModel：岛种类（is_statement/is_block 规则）、
               #   块起止符、每规则 FIRST 集、（可选）语句结束推导
  segment.py   # token 流 + IslandModel → 岛树（rule/span/children）+ water 区间
  markers.py   # 记号扫描（行注释语法取 lexer 配置；死分支水域取 scan_directives）
  process.py   # 岛文本 → 管线（parse+render，可选 transform/check）→ 片段文本
  splice.py    # 缩进基线回填 + 区间替换 + 后验（重解析/双跑幂等/字节 identity）
```

- **岛种类/边界/结束**全部来自 `build_slice_tree` + `Discovery` 的推导结果，引擎零
  语言知识；`[discovery]` 段里已有的语言事实（容器/延续等）同样被复用。
- **water** = 未被岛树覆盖的 token 区间 / 未识别区间 / 含宏与指令行的区间（后者不
  进管线，避免展开语义改动原文）；water 原样保留。
- **无记号**：P1 直接处理全文件推导出的所有岛（记号机制退役，见「P1 契约」）。

**已拍板（作者 2026-10-30，两项）**：

1. **推导层归属 → 留在 linter 内部**：`grammar_slicer / lookahead / discovery /
   discovery_shape` 不设独立顶层包（曾短暂抽离为 `structure/`，按作者决定并回）；
   它们是 linter 的内部组件，`islands/` 直接消费其推导 API。**例外**：FIRST/nullable
   是引擎通用算法（无语言知识），D10 尾项已下沉 `core/first_set.py`。
2. **声明面 → 不建**：不设 `[[island_rules]]`、不设 `island_rewriter` 能力位——片段模式
   下语法配置推导出的语法单元默认就是岛（见「P1 契约」）。
   若只想让某部分语法有效 → 单开语法包（作者定），不做记号/范围可选模式。

## P2/P3 契约与退出判据（立项后对照，防重考古）

**P2（安全与组合）**
- **范围作为对外接口**：`--lines`/`--offset` 形态（对齐 clang-format）与 LSP
  `textDocument/rangeFormatting` 形状的输出，编辑器只需给选区（选区 = 岛子集）；P1 的
  全域岛是默认入口，无需记号。
- 覆盖率报告 / `--json` / `--require-coverage`（字节口径）；`--verify full` 可选；文件级并行（基准后）；
- `inner-first` 外层重解析、默认平手拒绝策略的命中率统计；
- 真实语料（C + Verilog；SV 若可用）A/B：无规则 0 变化、有规则只改目标片段、输出可 parse 保持可 parse。
- **退出判据**：误改 0（负例集）、后验失败 0 落盘、双跑幂等、字节 identity 四例、性能达标、文档齐全。

**P3（与增量接合，可选）**：区域身份/内容 hash → 激活面实验；边界规则 → 延展实验；明确不替代
AST 并树；IDE 级增量另评 CST 路线。退出判据 = 增量只重查受影响片段且与全量结果一致（差分对拍）。

每阶段共同要求：文档同步、`Doc:` 反向引用、全量回归、pyright 清零、文档预算、**无默认行为变化**。
