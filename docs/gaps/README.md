# gaps/ — 缺口档案（Gap Files）

> 记录**能力缺口**的详细说明（具体级别）。宽泛条目 = `TODO.md` / `ROADMAP.md`
> 里的一行待办；详细级别（背景、为什么是缺口、成熟解法参照、可实现性、关联
> 条目）= 本目录每个缺口一个文件。TODO/ROADMAP 条目**链接过来**，正文不重复。

## 定位：与相邻目录的分工

| 目录 | 承载 | 与 gaps/ 的区别 |
|------|------|----------------|
| `gaps/` | **tpc 自己的缺口**（能力差 / 待闭环）：背景 + 参照 + 可实现性 + 关联条目 | 焦点 = "我们还缺什么、怎么补"，可含未成型讨论 |
| `references.md` | **外部项目事实/调研**（别人怎么做的调研 + 设计来源落档） | gaps 引用它做"参照来源"，不重复外部事实 |
| `decisions/` | **决策记录**（为什么这么定；draft = 未立项设计输入） | 缺口**立项要决策时** → 升 draft ADR；缺口文件不需决策骨架 |
| 架构文档 | 系统怎么拼（含功能缺口评估段） | 架构文档内"缺口 N"若独立成项 → 可摘出到 gaps/ 建档 |

一句话：**references 回答"别人怎么做"，gaps 回答"我们缺什么、怎么补"，ADR 回答"我们定了什么"**。

## 缺口文件模板

```markdown
# Gap — <缺口名>（<关联 TODO/ROADMAP 条目>）

- 状态：未立项 | 立项中 | 已闭环（闭环即删本文件）
- 关联：TODO.md / ROADMAP.md <条目>（宽泛条目侧链接到本文件）
- 参照：references.md / references/*.md <相关调研段>（外部事实源）

## 缺口是什么
能力差/待闭环的具体描述（够详细，避免下个 session 重新考古）。

## 为什么是缺口（影响面）
不补会怎样（覆盖盲区 / 场景受限 / 门禁缺口）。

## 成熟解法参照（见贤思齐）
外部工具怎么解决同一问题 → 借鉴点（🔥 直接借鉴 / 💡 启发 / 📌 路线观察）。

## 可实现性
方案形态 + 依赖前置 + 验证路径（拆几步、每步可独立验证）。

## 关联条目
- ROADMAP/TODO：<条目链接>
- 前置/后续：<其它条目>
```

## 生命周期（与 TODO"完成即删"同纪律）

- **立项启动** → 移回 `TODO.md` 短期，缺口文件升级为 draft ADR 或随实现吸收（删除/标注）。
- **已闭环** → 缺口文件**删除**（历史在 git log + CHANGELOG），不留 [x]。
- **不立项也不推翻**（长期）→ 本文件即承载（比 ROADMAP 段落可容纳更多详情）。

> 登记：本目录文件被 TODO/ROADMAP 条目或 `docs/README` 索引引用（check_doc_refs
> 防孤儿）；宽泛条目层（TODO/ROADMAP）只留一行 + 链接，不在此目录重复正文。

## 当前档案

> 聚合档（2026-09-04，原 docs 已知边界清单按部件拆入）：部件维度的
> 边界/缺口合集，条目级状态（接受/待闭环）+ 关联在档内标注；逐缺口单独立项
> 时再拆独立档。

| 缺口文件 | 关联条目 | 主题 |
|----------|----------|------|
| `gap-tpc-check-external-checker.md` | ROADMAP P2.6 | tpc-check 外部 checker 插件协议（接入 veryl/verible/slang + 自管场景） |
| `gap-lexer-capture-boundaries.md` | 原 known_limitations | lexer 捕获边界（块标量折叠/触发条件；多字符定界符 2026-09-12 已闭环） |
| `gap-parser-linter-approximation.md` | 原 known_limitations | parser/linter 错误处理近似（无恢复 + 启发式） |
| `gap-preprocessor-macro-boundaries.md` | 原 known_limitations | 宏覆盖缺口（type macros/复合嵌套反向映射） |
| `gap-renderer-comment-fidelity.md` | 原 known_limitations | renderer 注释回插保真（±3 行锚点启发式） |
| `gap-formatter-line-behavior.md` | 原 known_limitations | formatter 行行为边界（宽度折行/保留行/对齐/幂等） |
| `gap-language-pack-scope.md` | 原 known_limitations | 语言包范围与 yaml 边界（规模/SV/插件划分/增强语法） |
| `gap-semantic-elaboration-boundaries.md` | 原 known_limitations | 语义/插件契约（elaboration/单例/版本） |
| `gap-verification-engineering.md` | 原 known_limitations | 验证与工程边界（sample-driven/吞吐/增量/覆盖） |
| `gap-macro-diagnostic-mapping.md` | TODO.md「0.1.2 目标」 | 宏展开与诊断位置对应（行号回源 + 宏归因，成本已评估） |

> **2026-09-12 全员实测体检**：十档逐条实测核对（非照文档推断），状态修正已
> 就地落在每档 `- 状态：`；实测确认仍开放且可动手的六项已按序进入
> `TODO.md`「缺口闭环队列」逐项完成。本表**不复制状态**，避免第三处漂移。

> 新增缺口文件时：本表加一行 + `docs/README` gaps 索引补登记；闭环删除时同步移除。
