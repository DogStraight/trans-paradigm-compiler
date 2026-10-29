# Gap — 片段模式 P0（记号模式 / island rewrite 原型）

- 状态：**P0 完成（#70，2026-10-23）**；**P1 已获作者批准（2026-10-30）**，契约按「岛式分片」
  重述（见「P1 契约」节），未开工。
- 实现：`tools/fragment_rewrite.py`（独立 CLI `tpc fragment`，dry-run diff；`--write` 落盘）；测试 `tests/engine/test_fragment_rewrite.py`。
- 设计输入：已内联到本档「P1 契约」「P2/P3 契约与退出判据」节（原讨论稿随收尾销毁，不复用草稿路径）。
- 关联：`PROGRESS.md` 块 3；`ROADMAP.md`「当前主线」；`docs/gaps/gap-parser-linter-approximation.md`（parser 无错误恢复为刻意接受，本工具不改 parser）。

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

## P1 契约（岛式分片，作者 2026-10-30 批复）

**批复**：① 对外名 `tpc fragment` / 记号 `tpc:fragment` 定稿；② 批准新增 `[[island_rules]]`
声明段 + `island_rewriter` 能力位；③ **不做"改写规则集合"**——岛式分片 = 能解析/能变换的
区域进管线，管线输出替换原区间后合成，未处理部分原样保留；④ 记号按**语法岛**分片
（`end` 不要求 id）。

**为什么原稿有"规则集合"**：P0 用手写 `always @(*)`→`always @*` 证明标记与安全边界，P1
草稿沿用了这条演示规则、把它误当成骨架。实测管线本身**不做**该改写（CLI `format` 对
`always @(*)` 原样保留）⇒ 手写改写不是管线能力；P1 删除 `_find_always_star_edits`
（无兼容垫片，P0 原型随之淘汰）。

**实测边界（P1 判据的输入）**：

| 输入（单独喂管线） | 结果 |
|---|---|
| C `if (x) { y++; }` / Verilog `q = d;` | 成功，但输出缩进归零（合成须按插入位置重定基线） |
| C `} else { y++; }` / `int f(` / Verilog `endmodule` / `always @(*) begin` | lint 失败（不是完整语法单元） |

⇒ 岛必须圈**完整语法单元**；"哪些单元可解析/可变换"由语言包声明（岛类型），引擎不猜。

**`[[island_rules]]` 语义 = 岛类型声明（不是改写规则）**：

| 字段 | 含义 |
|---|---|
| `name` | 岛类型名（诊断/参数引用） |
| `marker` | 记号命名空间（默认 `tpc:fragment`；显式记号圈定区域） |
| `entry` | 岛入口：解析该岛的规则/块声明（如 `block_start`/`block_end` + 根规则） |
| `wrapper` | 可选：把岛补成完整单元的模板（缺省 = 岛本身按根规则 parse） |
| `pipeline` | 管线面：默认 `parse+render`；`transform`/`check` 须显式 opt-in（依赖岛外上下文，判据 = 与全文件同片段结果一致） |
| `merge` | 合成策略：`reindent`（按插入位置重定缩进基线，默认）/ `verbatim` |

**能力位**：`island_rewriter` 组件 handler（`[capabilities] island_rewriter = <component>`；
能力表项 `capability.island_rewriter`）——引擎只做"岛文本 → handler → 片段文本"调用与合成
后验（重解析 / 双跑幂等 / 字节 identity），不写任何语言规则。

**合成契约**：岛输出替换原区间；管线失败或未命中的岛**原样保留**（fail-closed）；标记行本身
不进岛内容；无岛或零变化 ⇒ 逐字节返回原 bytes；编辑区间重叠/未配对/嵌套 ⇒ 不落任何编辑。

**记号**：`// tpc:fragment begin` … `// tpc:fragment end`（单层、标记独占行）；id 可选，
若 begin/end 都带 id 则必须一致（错配 fail-closed）；同行 begin/end 不支持（P2 再评）。

**P1 验收**：Verilog（module-item `always` 块、语句）与 C（函数体语句块、声明）各 ≥2 类真实
岛经管线 + 缩进回填；负例（非语法单元 / 未配对 / 嵌套 / 管线失败）不落编辑；双跑幂等；无岛
文件字节 identity；全量回归不绿不算完成。

## P2/P3 契约与退出判据（立项后对照，防重考古）

**P2（安全与组合）**
- 覆盖率报告 / `--json` / `--require-coverage`（字节口径）；`--verify full` 可选；文件级并行（基准后）；
- `inner-first` 外层重解析、默认平手拒绝策略的命中率统计；
- 真实语料（C + Verilog；SV 若可用）A/B：无规则 0 变化、有规则只改目标片段、输出可 parse 保持可 parse。
- **退出判据**：误改 0（负例集）、后验失败 0 落盘、双跑幂等、字节 identity 四例、性能达标、文档齐全。

**P3（与增量接合，可选）**：区域身份/内容 hash → 激活面实验；边界规则 → 延展实验；明确不替代
AST 并树；IDE 级增量另评 CST 路线。退出判据 = 增量只重查受影响片段且与全量结果一致（差分对拍）。

每阶段共同要求：文档同步、`Doc:` 反向引用、全量回归、pyright 清零、文档预算、**无默认行为变化**。
