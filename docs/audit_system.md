# 审计制度（Audit System）

> 一句话：**一套可插拔的审计管线**——槽位固定、环节可换，判据是否仍成立由人判。
> 目的不是"把问题查完"（问题空间开放，永远查不完），而是**每一轮能关掉一个维度并冻结**。

数据面：`docs/audit_dimensions.toml`（维度 + 槽位 + 本版闭合目标）
制度正文：`policy/collaboration.md`（任务循环四条规则 + 「审计维度轮」）
执行器：`tools/audit_cycle.py`（只收集，不裁决）
判断协议：`~/.agents/skills/invariant-falsifier`（证伪器，非检测器）

## 1. 为什么这样设计

三个失败模式驱动，每个都在这套制度里有对应位置：

| 失败模式 | 表现 | 制度里的对策 |
|---|---|---|
| **枚举幻觉** | 用词表/分支逼近开放集，每来一个新案例补一条 | 维度（有限）替问题清单（开放）；新机制须过**删除测试** |
| **静默降级** | 跳过/丢弃不记录，门禁照常绿 | 每维 `closure` 声明；"无探针不得判关闭"；探针失效须人判 |
| **假绿** | 门禁存在但永不响；测试因错误原因通过 | `evidence_kind`：散文证据不得支撑"需重新设计"级结论 |

第四条最要紧：**审计不能完全外包给探针**。探针是半固化的代理，被闭开原则淘汰后
仍会安静地返回 PASS——比没有探针更危险。所以判据有效性做成人工复核项。

## 2. 五层结构

| 层 | 内容 | 是否随项目变 |
|---|---|---|
| 数据 | `docs/audit_dimensions.toml`（维度/槽位/目标） | **变**（换项目换数据） |
| 协议 | `policy/collaboration.md`「审计维度轮」 | 稳定（四条规则语义不变） |
| 执行 | `tools/audit_cycle.py` + 各维度探针脚本 | 稳定（按需插拔） |
| 判断 | 构造反例 + 证据种类（人/模型） | 不可外包 |
| 自省 | `docs/audit-retro.jsonl`（每轮 1 条改进候选） | 累积后动制度 |

## 3. 槽位（可插拔管线）

管线骨架固定，环节可换。槽位三态：

| `impl_kind` | 含义 | 校验 |
|---|---|---|
| `file` | 仓内实现 | 路径必须存在 |
| `external` | 外部能力（如用户级 skill） | 不校验路径 |
| `todo` | 空槽留白 | **必须写 `trigger`**（何时该填） |

当前槽位：

| 槽位 | 状态 | 职责 |
|---|---|---|
| `collect` | 装载 | 跑探针，只出候选不裁决 |
| `judge` | 装载 | 构造最小反例 + 给证据种类 |
| `close` | 装载 | 每维闭合判据 + 关闭即冻结 |
| `record` | 装载 | 落账（含人判结论、可回溯趋势） |
| `retro` | 装载 | 每轮 1 条制度改进候选（可为「无」） |
| `autofix` | **卸载（仍在册）** | 留白：同类机械返工连续 3 轮再填 |

**卸载 = 把 `enabled` 翻成 `false`，槽位仍在册**——不许用删除表达"当前不需要"。
（门禁 `test_disabled_slots_are_not_deleted` 强制至少保留一个留白槽位。）

## 4. 维度（审什么）

9 个维度，4 个来自作者核心任务、5 个来自审计中发现的新失效模式：

| ID | 维度 | 来源 | 探针 |
|---|---|---|---|
| D1 | 冗余内容文件 | 作者 | `tools/scan_redundant.py` |
| D2 | 机制正交性 | 作者 | `tools/structural_score.py` |
| D3 | 测试用例正交性 | 作者 | `tools/scan_test_redundancy.py` |
| D4 | 缺口文档冗余 | 作者 | `policy/check_doc_refs.py` |
| D5 | 门禁有效性（假绿） | 审计 | todo（改门禁时必须补变异） |
| D6 | 静默降级（fail-open） | 审计 | todo（发现一次即补） |
| D7 | 测试断言强度 | 审计 | todo（出现"全绿没拦住"即补） |
| D8 | 基线/账本腐化 | 审计 | `tests/policy/test_structural_kept.py` |
| D9 | 跨平台与编码假设 | 审计 | todo（出现平台相关失效即补） |
| D10 | 逐部件冗余代码（最小形式） | 审计 | `tools/scan_redundant_code.py` |

每个维度必须声明三样（门禁强制）：

- `proxies`：这个探针**代理的是哪条性质**（不是它输出什么）
- `invalidated_if`：**什么变化会让这个代理失效**
- `closure`：关没关怎么判

还活着的遗留项不另设台账：写在该维度的 `pending`（一句话 + 判据），
关闭时并入 `closed_evidence` 并删掉 `pending`——不允许两处各说一套。

## 5. 一轮怎么走

不是新流程——是任务循环四条规则的特化：

```
规则1 取任务  → 取一个维度（status=open），一轮最多关 1–2 个
   ↓ 开局先做「探针有效性复核」（人判，不可外包）
规则2 计划    → 判据 = 该维 closure + 探针命令；无探针不得判 closed
规则3 验证    → 重跑探针 + 按影响范围取测试 + 三个基线数字前后对照
               （structural S / 诊断基线 / lint 召回）
规则4 收口    → audit_cycle.py --ledger --judgement --retro 三件套落账；
               维度满足四条判据 → 标 closed 并**冻结**
```

**关闭四条判据**（缺一不可）：findings 全关且有可复跑证据 / 探针存在 /
全量门禁绿 / 基线不劣化。

**关闭即冻结**：此后只有"先出现失败用例"才允许解冻——防止"顺手改进"无限循环。

## 6. 证据规则

| 规则 | 内容 |
|---|---|
| 反例优先 | 没有反例的 finding 一律丢弃（"我觉得不太好"不许输出） |
| 证据分级 | `executable`（可复跑）才允许"需重新设计"级结论；`prose` 最高"需修订" |
| PASS ≠ 关闭 | 探针返回 0 只说明命令成功，不等于维度已关闭 |
| 净零 ≠ 无变化 | 基线"不涨"不代表无变化，须给同一指标前后值 |
| 假绿五问 | 见下节（本版用它**替代**原「判据五问」：把"有区分力/靠什么绿"并入第 1、2 问） |

### 6.1 假绿五问（每轮收口前逐条过，答不上来就不许关）

1. **这个绿是证明了它，还是绕过了它？** 端到端还是只测了单点——`test_*` 绿可能因为只调 helper，
   而入口根本没接（实测：`main.py` 入口没调 `ensure_utf8_stdio`，cp936 下 `--tree` 直接坏）。
2. **量具死了，谁会红？** 基线项全消失、扫描面为 0、报表为空串——三种都要能红
   （`INV-RATCHET-NOT-VANISH`；`check_platform_encoding.MIN_PY_FILES`）。
3. **这条判据在哪一行代码/测试里被强制执行？** 声明的「必须/一律/判据是」若找不到执行点，
   就是**没有判据**（实测：`.gitattributes` 写了 LF 却无门禁，102 个文件 CRLF，
   字节级变异锚点静默失配）。
4. **同一个形状还有几个兄弟？** 修一处必须扫一遍同类（实测：ratchet 一处 → 4 处；
   stdout 副本一处 → 11 处；CRLF 43 个 → 102 个）。
5. **我报的数字拆过账吗？** 记账（判保持/基线重录）与真实收益必须分开报
   （实测：S −256 里 −97 是记账；再往下 −159 还算错，真值 −141）。

> 这五问产出**可复跑反例**才算数；散文结论只能算线索（见上方证据分级）。

### 6.2 模型高频缺陷：已机械化 vs 只能靠审查提示

**已进入 `policy/`（有可执行判据）**

| 缺陷 | 判据 |
|---|---|
| 吞异常（`except Exception: pass`） | `policy/check_exception_hygiene.py`：宽异常必须写理由、禁裸 `except:` |
| 门禁量具死了仍报绿 | `INV-RATCHET-NOT-VANISH`（`tools/_ratchet.py`，四处接入） |
| 门禁被改弱/变异失效 | `tools/check_gate_efficacy.py`（126 条变异，每条要能红） |
| 平台/编码假设 | `tools/check_platform_encoding.py`（E1–E4）+ `tests/policy/test_eol_normalized.py` |
| 语言知识写进引擎 | `policy/check_hardcode.py` R1–R6 + `tools/lang_penetration.py` |
| 重复实现 / 结构欠账 | `tools/structural_score.py` + `tools/feature_sites.py`（新增即红） |

**只能靠审查提示（无静态判据，写进每轮检查清单）**

1. **Oracle 自证**：期望值是不是从实现跑出来粘进去的？——要问"这个 expected 来自哪份规格/语料"。
2. **测试抄实现**：测试里出现与实现相同的常量表/分支链 → 至少一处断言必须来自外部数据。
3. **注释语义不符**：具体措辞（排序稳定/幂等/只读）有 `check_claim_*` 之外的**语义级**漂移，只能人读。
4. **估算冒充测量**：阈值有没有出处？`tools/threshold_sweep.py` 只出表，"够不够"仍要人判。
5. **静默默认链**：`raw.get(k, {})` / `getattr(x, k, None)` 一层层加，配置写错不报错。
6. **过拟合测试**：为过某个用例加特判（按测试文件名/样例内容分支）。
7. **无界缓存**：模块级 memo 只增不减。
8. **并发/重入**：模块级可变状态、单例、可重入假设。
9. **忽略返回值**：`subprocess` 不看 returncode、布尔结果被丢。
10. **过度包装**：只做转发的适配层，删掉调用方照样正确。

## 7. 制度自身不闭合（只本版有闭合目标）

制度是管线，不是定稿：槽位可插拔、维度可增删、改进走 `retro` 账本累积后再动。
**本版就绪的闭合目标**（`docs/audit_dimensions.toml` 的 `[[goal]]`，met 必须附存在证据）：

| 目标 | 内容 |
|---|---|
| G1 | 槽位三态合法（file/external/todo+trigger） |
| G2 | 装载/卸载只改数据 |
| G3 | ≥2 槽位有真实实现且被跑过 |
| G4 | retro 每轮产出 1 条（可为「无」），不改制度本身 |
| G5 | 全量门禁绿且结构分不劣化 |

明确不做：全自动闭环、一次性补全所有槽位、制度版本号/发布流程。

## 8. 和其他机制的分工

| 机制 | 只回答 |
|---|---|
| 本制度（审计维度轮） | 这一轮关哪个维度、关没关 |
| `invariant-falsifier` | 这个候选算不算真问题（反例 + 证据） |
| `policy/pylance-cleanup.md`「补丁 vs 机制」 | 这次改动是补丁还是机制（三句自查；原 `enumeration-illusion-audit` 判据已并入） |
| `docs/invariants.toml` | 判据本身是否还成立 |
| `policy/check_hardcode.py` / `check_doc_refs.py` | 具体的机器化硬约束 |

## 9. 已知局限

1. **探针是代理**：会随闭开原则腐化；腐化后仍返回 PASS。对策 = 每轮人判
   `proxies` / `invalidated_if`，结论入账本（`--judgement`）。
2. **形式主义风险**：探针全绿但无人看结论。对策 = 账本每轮必须有 `closed`
   或 `findings>0`；连续两轮全绿且无 findings 视为该维度已稳定，降为按需跑。
3. **`branch_chain` 类探针无法区分"按类型分派（合法）"与"按形态堆规则（补丁）"**：
   须人判，不能只看严重度。
4. **4 个维度仍无探针**（D5/D6/D7/D9）：登记为 todo + trigger，触发条件到了再补；
   无探针维度不得判 closed（门禁强制）。

## 10. 命令速查

```bash
python tools/audit_cycle.py --list                 # 看维度与槽位状态
python tools/audit_cycle.py --dim D2               # 跑单维探针
python tools/audit_cycle.py --ledger docs/audit-ledger.jsonl \
    --judgement "开局复核：D1-D4 探针仍有效" --retro "本轮改进候选"
python -m pytest tests/policy/test_audit_dimensions.py -q   # 注册表门禁
python policy/check_invariants.py                  # 不变量清单门禁
```
