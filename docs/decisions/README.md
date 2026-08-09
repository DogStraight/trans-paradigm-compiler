# Architecture Decision Records（ADR）

> 记录"为什么这么定"，而非"是什么/怎么拼"（那属于 architecture/）。
> 每条 ADR 是讨论痕迹的沉淀——模型维护时通过 `Impl:`/`Test:` 直接跳转到代码，无需模糊搜索。

## 编号规则

- 文件名：`NNNN-<kebab-case-主题>.md`，`NNNN` 从 `0001` 递增，逆序展示（最新在上）。
- 已废弃/被推翻的决策标记 `Status: superseded by NNNN-xxx`，不删除（保留历史）。

## 条目模板

```markdown
# ADR-NNNN: <决策标题>

- Status: accepted | superseded by NNNN-xxx
- Date: YYYY-MM-DD

## 背景
为什么需要决策（问题/事故/动机）。

## 决策
定了什么，明确到可执行。

## 权衡
付出了什么（成本/被拒绝的备选）。

## 验证
如何证明决策有效（测试/数据）。

> Impl: <代码路径>::<符号>   （实现位置，供模型直接跳转）
> Test: <测试路径>            （验证位置）
```

## 对齐约定

- 代码文件头 docstring 加 `Doc: docs/decisions/NNNN-xxx.md` 反向指向。
- 模型改造某子系统前：查 `docs/MODEL_INDEX.md` 跳转表 → 读对应 ADR/架构文档 → 跳 `Impl:` 位置。
