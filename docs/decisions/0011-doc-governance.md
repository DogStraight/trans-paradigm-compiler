# ADR-0011: 文档治理（调用点门禁 + 同步层 + 删除判据）

- Status: accepted（门禁 check_doc_refs / 同步 doc_sync 已实现；删除判据作
  协作方清单生效）
- Date: 2026-09-02（设计）；2026-09-02（自 docs/references.md 迁入）
- Supersedes: references.md 同章节（内容迁移，非推翻）

## 背景

docs 精简（35→29 文件）暴露文档管理痛点——文档增删改时调用点（代码
`Doc:` 头 114 处 / MODEL_INDEX 与 docs-README 索引 / `Impl:`/`Test:` 42 处）
全靠人工 grep 核对；check_hardcode 的 R3 只查 `Doc:` 头**格式**（正则存在），
不查**目标文件存在**——删文档门禁照样绿。另有"什么该删"长期凭临场判断
（有删除原则但无判据层），是注释/文档/代码膨胀的方法论根源。

目标：机械可判的引用完整性 → 自动门禁；语义判断（符号级/章节锚点）留给
人工/模型；删除动作有显式判据（先证后删）。

## 决策

### 1. 文档调用点门禁（已实现：policy/check_doc_refs.py）

分两层：**门禁层**（只读校验，进 CI，与 check_hardcode 并列）+ **同步层**
（rename/delete 辅助写操作，不进 CI）。门禁规则：

- D1 [gate] 代码 `Doc:` 头 → 目标 docs 文件存在（补 check_hardcode R3 缺口）
- D2 [gate] 导航索引（MODEL_INDEX / docs-README / README 文档表）→ 条目存在
- D3 [info] docs 内 `Impl:`/`Test:` → 文件级存在（`::` 符号部分 info 不 gate）
- D4 [info] 新增 docs 文件未登记任何导航 → 警告（孤儿提醒，不阻断）

明确不做（边界纪律，与"语言知识不进代码"同构——语义判断不进工具）：
符号级存在性（须 import 代码，脆且重）；CHANGELOG 历史条目自动改；正文
叙述引用自动替换（`references.md「章节」` 含锚点语义）。

### 2. 同步层（已实现：policy/doc_sync.py）

门禁层解决"断链被发现"；同步层解决"改名/删除时调用点一起改"——复用
check_doc_refs 的引用解析（同一组正则 + `_resolve_nav_target`），保证
"门禁认的引用 = 同步层改的引用"，两边不漂移。

子命令（全部默认 --dry-run 只报告，--apply 才落盘）：
- `refs <target>`：列出某 docs 文件被谁引用，每处 文件:行 + 引用形态
- `rename <old> <new> [--apply]`：改 docs 文件路径 → 同步改全部引用点
- `delete <target> [--apply]`：删除 docs 文件 → 先列引用点，--apply 时
  同步清引用（原子性：任一引用非机械可清即完全不动）

### 3. 删除判据（协作方清单，AGENTS.md 硬约束简版 + 本 ADR 全表）

**先证后删**：每条删除必须能指出命中哪条判据 + 证据（grep 零引用 /
diff 等价 / 权威源存在 / 目标不存在）。说不出判据的删除不做。

#### 代码删除判据

| # | 判据 | 证据 |
|---|------|------|
| A1 | 无引用死代码 | grep 零调用/零导入 |
| A2 | 双实现（功能重复） | 另一处等价或超集（diff） |
| A3 | 决策已变的过时实现 | git log + ADR/落档 |
| A4 | 归属错 → **移动非删** | 目录职责表 |
| A5 | 结构不一致（编号/形态） | 与同类目录形态对比 |

#### 注释/docstring 删除判据

| # | 判据 | 证据 |
|---|------|------|
| B1 | 零信息增量（复述代码/空话） | 删除后信息零损失 |
| B2 | 与权威源重复（清单/罗列） | 权威源存在（api.md/架构文档） |
| B3 | 引用已删目标（过时事实） | 目标不存在（D1 门禁可抓） |
| B4 | 编辑残留（双 docstring/路径注释） | 结构异常（连续两个 docstring） |
| B5 | 过时注记（待补已补/路径已变） | 注记所指状态已变化 |

#### 文档删除判据

| # | 判据 | 证据 |
|---|------|------|
| C1 | 一次性计划已完成 | docs/README 纪律（成果入 CHANGELOG） |
| C2 | 与代码漂移且无维护 | D3/D4 门禁辅助 + 内容对照 |
| C3 | 与权威文档重复 | 单一权威源原则 |
| C4 | 版权/外部分发风险 | MANIFEST 排除先例 |

#### 反判据（不是删除理由——防误删）

| # | 反判据 | 理由 |
|---|--------|------|
| X1 | "看起来没用"（无证据） | 违反先证后删 |
| X2 | 历史调研/决策记录（references.md/ADR） | 落档纪律：git log 无法承载"为什么" |
| X3 | 个人思考沉淀 | 分层纪律：不对齐不套删除约定 |
| X4 | CHANGELOG 历史条目 | 发布记录不可篡改 |

## 权衡

- 门禁/同步层选"复用 check_hardcode 同构"而非新框架——零新依赖、门禁
  形态一致（Finding/RuleResult/--root/exit-code）。
- 删除判据作清单不作门禁（用户拍板）：能机器判的进门禁（D1 已抓 B3），
  不能的进清单——不新增自动检查（误报面需先评估）。
- 边界：语义判断（符号级/锚点/正文叙述）不进工具，留人工/模型。

## 验证

- 门禁：`tests/policy/test_check_doc_refs.py`（24 用例）+ `test_doc_sync.py`
  （15 用例），含真实仓库 D1/D2 零违规回归。
- 删除判据：清理任务收尾用判据表复盘，未命中判据的删除回滚或补证据。

> Impl: policy/check_doc_refs.py（D1-D4）
> Impl: policy/doc_sync.py（refs/rename/delete）
> Test: tests/policy/test_check_doc_refs.py / test_doc_sync.py
