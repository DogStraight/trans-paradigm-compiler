# 审计循环（Audit Loop）

> 数据面：`docs/audit_dimensions.toml`（审什么 + 判据 + 探针）
> 证伪面：`~/.agents/skills/invariant-falsifier`（怎么判"这是不是真问题"）
> 不变量面：`docs/invariants.toml`（判据本身是否成立）

## 为什么是循环而不是清单

清单问"还有哪些问题没查"——问题空间开放，永远查不完，最后变成无限追加。
循环问"这一轮我要**关闭哪个维度**"——维度有限、可判定、有闭合条件。

**每一轮只允许关闭 1–2 个维度**，且关闭后该维度**冻结**（只在新反例出现时解冻）。
这是本循环唯一防止"无休止改动"的机制。

## 阶段（S0–S6）

```
S0 选维度     从注册表挑 1–2 个 status=open 的维度（按"错了会不会静默浪费"排序）
S1 跑探针     python tools/audit_cycle.py --dim D<N>   → 候选（只出候选，不裁决）
S2 证伪       对每个候选构造最小反例；按 invariant-falsifier 输出
              findings[invariant, counterexample, evidence, evidence_kind]
              散文证据（prose）不得支撑 needs_redesign
S3 修复       单一来源优先；新机制必须过删除测试（删掉它旧机制是否仍独立正确）
S4 复验       重跑该维度探针 + 全量门禁 + 基线差值（S/Diag/Lint 三个数字）
S5 落账       python tools/audit_cycle.py --ledger docs/audit-ledger.jsonl
S6 闭合判定   满足下列全部 → 该维度标 closed 并冻结：
              ① 该维度 findings 全部关闭且证据可复跑
              ② 探针命令存在（无探针不得关闭：见注册表硬规则）
              ③ 全量门禁绿（check_hardcode / check_doc_refs / check_invariants / pytest）
              ④ 基线数字不劣化（S 不增；诊断基线不涨；lint 召回不降）
```

## 每轮的产出（必须可复核）

| 产出 | 为什么 |
|---|---|
| 探针输出（原始） | 不然"我查过了"无法复核 |
| findings + `evidence_kind` | 区分"可执行证据"与"我的判断" |
| 修复前后的基线数字 | 净变化为 0 ≠ 无变化，必须给同一指标前后值 |
| 账本一行 | 让"维度是否只增不减"可见 |

## 维度增删规则

- **新增维度**必须同时给出 `probe` 或 `trigger`（否则是黑洞）。
- **删除维度**必须写明它被哪条不变量/哪个维度吸收（禁止裸删）。
- 维度总数**不应持续增长**：新维度优先并入既有维度，而不是并列新增。
  这本身受 `INV-EVOLUTION` 约束。

## 与其他机制的分工

| 机制 | 回答什么 |
|---|---|
| 审计循环（本文件） | 这一轮关哪个维度、关没关 |
| invariant-falsifier | 这个候选算不算真问题（反例 + 证据） |
| enumeration-illusion-audit | 这段代码里有没有"表/分支链"（候选发生器，已冻结） |
| docs/invariants.toml | 判据本身是否还成立（清单不许腐烂） |

## 反身性

循环本身也会腐化：探针全部"绿"但没人看结论 = 形式主义。
校验方式：账本里每轮必须有 `closed` 或 `findings>0`，**连续两轮全绿且无 findings**
视为"该维度已稳定"，应把它从每轮必跑降为按需跑（降低审计成本，不是降低标准）。

Doc: docs/audit_dimensions.toml
