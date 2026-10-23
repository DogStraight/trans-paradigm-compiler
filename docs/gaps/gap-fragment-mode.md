# Gap — 片段模式 P0（记号模式 / island rewrite 原型）

- 状态：**P0 完成（#70，2026-10-23）**；P1（声明面/能力位）**待作者批准**，未开工。
- 实现：`tools/fragment_rewrite.py`（独立 CLI `tpc fragment`，dry-run diff；`--write` 落盘）；测试 `tests/engine/test_fragment_rewrite.py`。
- 设计输入：`_drafts/marker-mode-evaluation.md`（未入库；P0/P1/P2 分期与契约面约束）。
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

## P1 开工前需作者拍板（框架级）

1. 对外名：`tpc fragment` / 记号命名空间 `tpc:fragment`（内部名 `fragment rewrite`，不用 island）是否定稿？
2. 批准新增 `[[island_rules]]` 声明段 + `island_rewriter` 能力位？（新配置 schema/组件类型 = 框架级，须先批）
3. 规则集/优先级：P1 先做 Verilog `always @(*)`→`always @*` + 事件列表 `or`→`,` 两条？冲突默认 priority 平手拒绝？
4. `end` 记号是否需要 id 匹配（P0 不要求）；记号是否允许同行 begin/end（P0 不支持）？

未获批准时 P0 保持独立工具、不动默认行为；批准后按草稿 P1（语法驱动+插件+后验）实施。
