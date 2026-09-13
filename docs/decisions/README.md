# Architecture Decision Records（ADR）

> 记录**已生效的决策**（为什么这么定），而非"是什么/怎么拼"（那属于机制文档）。
> 每条 ADR 是讨论痕迹的沉淀——模型维护时通过 `Impl:`/`Test:` 直接跳转到代码，无需模糊搜索。
> 落档分流（AGENTS.md）：外部项目调研落 references.md；执行结果落 CHANGELOG + 测试；
> 未成型的讨论 / 未立项设计输入**不进本目录**（`_drafts/` 或 ROADMAP 条目承载，
> 立项定案时才建 ADR）。
> **引用纪律**：decisions/ 是经常变动的部分（accepted 完成即删、编号可复用、
> draft 并入 ROADMAP 后删）——代码 Doc:/导航/正文不引 ADR 作锚，引稳定的机制
> 文档；机制文档内联"为什么"，不写"见 ADR-NNNN"（详见 policy/doc-alignment.md
> 「引用纪律」）。

## 入档与删除（防堆积）

- **只在决策成立时建档**：候选方案 / 未立项设计输入走 `_drafts/` 或 ROADMAP
  条目详案，不进 decisions/。
- **完成即删**：决策实现并被机制文档 / 测试吸收后删除本档（历史在 git log）；
  删除前先确保机制已落部件文档（子包 README / 架构文档）。
- **被推翻**：直接删（历史在 git log），不留 superseded 链。
- 删除判据见 `policy/doc-alignment.md`。

## 编号规则

- 文件名：`NNNN-<kebab-case-主题>.md`，`NNNN` 从 `0001` 递增，逆序展示（最新在上）。
- 状态：`accepted`（已决策/实现中）。

## 条目模板

```markdown
# ADR-NNNN: <决策标题>

- Status: accepted
- Date: YYYY-MM-DD

## 背景
为什么需要决策（问题/事故/动机）。

## 决策
定了什么，明确到可执行。

## 权衡
付出了什么（成本/被拒绝的备选）。

## 验证
如何证明决策有效（测试/数据）。

> Impl: <代码路径>::<符号>
> Test: <测试路径>
```

## 对齐约定

- 改造某子系统前：查 `docs/MODEL_INDEX.md` 跳转表 → 读对应机制文档 → 跳 `Impl:` 位置。
- 代码**不反向引用 ADR**（引用纪律见 `policy/doc-alignment.md`）。
