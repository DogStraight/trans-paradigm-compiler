# Architecture Decision Records（ADR）

> 记录"为什么这么定"，而非"是什么/怎么拼"（那属于 architecture/）。
> 每条 ADR 是讨论痕迹的沉淀——模型维护时通过 `Impl:`/`Test:` 直接跳转到代码，无需模糊搜索。
> 落档分流（AGENTS.md）：设计/研判（含未立项设计详案）建 ADR；外部项目调研
> 落 references.md；执行结果落 CHANGELOG + 测试。

## 状态流：讨论 → 决策（防堆积、防蒸发）

开放讨论（还没到"可立项设计输入"阶段的取舍/想法）与 ADR 的关系：

- **未成型讨论不进 decisions/**——decisions/ 是决策记录，不是草稿箱。物理承载 =
  `_drafts/`（根目录讨论草稿暂存区：不进 git、门禁排除，见 AGENTS「文档放置速查」）
  + 作者与模型的协作会话/会话笔记。**成型判据**：形成可立项的「问题 + 候选方案 +
  取舍」→ 建 draft ADR（未立项设计输入，常作 ROADMAP 项详案）。
- **防蒸发**：讨论中已探明的机制事实（"本次实测确认、不应再次考古"的结论）
  即便未立项，也随 draft ADR 固化——避免下个 session 重复源码考古。

draft ADR 生命周期（三出路，避免"僵尸 draft"堆积）：
- **立项实现** → `Status: accepted`，`Impl:`/`Test:` 补实。
- **被推翻 / 不采纳** → `Status: superseded by NNNN-xxx`（保留历史，不删除）。
- **长期搁置**（不立项也不推翻）→ 把方向注记并入 ROADMAP 对应条目后**删除**
  （decisions/ 不堆未立项详案；历史在 git log 可追溯，与 TODO"完成即删"同纪律）。

> 关联：落档分流见 AGENTS.md（调研→references / 设计→ADR / 执行→CHANGELOG）；
> 删除判据见 `decisions/0011-doc-governance.md`。

## 编号规则

- 文件名：`NNNN-<kebab-case-主题>.md`，`NNNN` 从 `0001` 递增，逆序展示（最新在上）。
- 状态三态：`accepted`（已决策/实现）/ `draft`（未立项设计输入，ROADMAP 项详案）/
  `superseded by NNNN-xxx`（被推翻，不删除保留历史）。
- **draft → accepted**：立项实现时升状态；draft 的 `Impl:`/`Test:` 可标"待实现"。

## 条目模板

```markdown
# ADR-NNNN: <决策标题>

- Status: accepted | draft | superseded by NNNN-xxx
- Date: YYYY-MM-DD

## 背景
为什么需要决策（问题/事故/动机）。

## 决策
定了什么，明确到可执行。

## 权衡
付出了什么（成本/被拒绝的备选）。

## 验证
如何证明决策有效（测试/数据）。

> Impl: <代码路径>::<符号>   （实现位置，供模型直接跳转；draft 可标"待实现"）
> Test: <测试路径>            （验证位置）
```

## 对齐约定

- 代码文件头 docstring 加 `Doc: docs/decisions/NNNN-xxx.md` 反向指向。
- 模型改造某子系统前：查 `docs/MODEL_INDEX.md` 跳转表 → 读对应 ADR/架构文档 → 跳 `Impl:` 位置。
