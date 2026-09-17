# gaps/ — 缺口档案（Gap Files）

> 记录 tpc **当前仍成立**的能力边界/缺口（接受项 + 未闭环项）的详细说明。
> **只记本体**：现状陈述 + 关联条目——不记过程（立项、体检、复核、闭环流转；
> 历史在 git log + CHANGELOG）。待办本身在 TODO/ROADMAP 一行 + 链到本档。

## 定位：与相邻文档的分工

| 位置 | 承载 | 与 gaps/ 的区别 |
|------|------|----------------|
| `gaps/` | tpc 自己的**能力边界/缺口**现状（接受项 + 未闭环项） | 焦点 = "我们现状差什么、还缺什么" |
| `references.md` | **外部项目事实/调研**（别人怎么做的调研 + 设计来源落档） | gaps 引用它做"参照来源"，不重复外部事实 |
| `decisions/` | **生效中的决策**（为什么这么定） | 缺口立项决策时建 ADR；本档不写决策骨架 |
| 机制文档 | 系统怎么拼（含功能缺口评估段） | 机制文档内"缺口 N"若独立成项 → 可摘出到本档 |

一句话：**references 回答"别人怎么做"，gaps 回答"我们现状差什么"，ADR 回答"我们定了什么"**。

## 档案模板

```markdown
# Gap — <主题>（<关联 TODO/ROADMAP 条目，若有>）

- 状态：接受（设计选择/范围） | 未立项 | 未闭环（剩 N 项）
- 关联：<TODO/ROADMAP 条目；相关机制文档>
- 参照：references.md <相关调研段>（外部事实源，可选）

## 边界是什么（或：缺口是什么）
当前仍成立的陈述（够详细，避免下个 session 重新考古）。
未闭环项附：为什么是缺口/影响面；接受项附：为什么接受。

## 成熟解法参照（见贤思齐，未闭环项适用）
外部工具怎么解决 → 借鉴点（🔥 直接借鉴 / 💡 启发 / 📌 路线观察）。

## 可实现性（未闭环项适用）
方案形态 + 依赖前置 + 验证路径（拆几步、每步可独立验证）。

## 关联条目
- <TODO/ROADMAP 链接、机制文档、测试门禁>
```

## 更新纪律

- **条目消失（修好/不再成立）→ 直接删条目或整档**（历史在 git log +
  CHANGELOG），不写"已修复/已闭环"注记。
- 登记：本目录文件被 `docs/README` 索引引用（check_doc_refs 防孤儿）；
  新增档案本表加一行，删除同步移除。

## 当前档案

| 档案 | 主题 |
|------|------|
| `gap-tpc-check-external-checker.md` | tpc-check 外部 checker 插件协议（接入 veryl/verible/slang + 自管场景；ROADMAP P2.6） |
| `gap-lexer-capture-boundaries.md` | lexer 捕获边界（块标量折叠/chomping 不语义化、触发条件限声明式） |
| `gap-preprocessor-comment-scan.md` | 预处理器注释扫描（行级状态机近似：字符串内定界符、注释后同行指令） |
| `gap-parser-linter-approximation.md` | parser/linter 错误处理近似（无恢复 + 启发式） |
| `gap-formatter-line-behavior.md` | formatter 行行为边界（宽度折行/保留行/对齐/幂等） |
| `gap-language-pack-scope.md` | 语言包范围与 yaml 边界（规模/SV/插件划分/增强语法） |
| `gap-semantic-elaboration-boundaries.md` | 语义/插件契约（elaboration/单例/inject） |
| `gap-verification-engineering.md` | 验证与工程边界（sample-driven/吞吐/增量/覆盖） |
