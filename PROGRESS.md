# 进度条 — 主线 2：工具化 + 高性能（0.1.4）

> **用途**：回答"到 0.1.4 还有多少进度"的单一视图（2026-10-23 立，替代已收口的主线 1）。
> **只记刻度与判据状态**：不记过程（→ `CHANGELOG.md`）、不记待办（→ `TODO.md`）。
> **数字口径**：未通过数（skip/xfail/失败）必记；通过数只给复现命令。
> **更新时机**：每轮收口更新刻度 + 「下一轮入口」（三行，替换不追加）。
> 上限 60 行（`tests/policy/test_planning_doc_budget.py`）。

## 分界线

主线 1（C 包框架缺口 9/9）与 T1–T3（#51–#66）已收口；本档改记 **主线 2 = 0.1.4 高性能 + 工具化**。
历史见 `CHANGELOG.md` / git log，不复述。

## 刻度（分母 = 12 块）

| # | 块 | 状态 |
|---|----|------|
| 1 | **基线清算** | ✅ 三探针：S Δ0、feature 0、config_sites PASS（TODO 过期三项已清，`864e472`） |
| 2 | **parser 性能收口** | ✅ atom memo + FIRST 早拒（#68/#69）：cJSON 57.6→**2.98s**（19.3x）；门禁 **20–23s**；A/B 0/144、全量 4377/14、7/7 0 诊断 |
| 3 | **片段模式 P0** | ✅ 独立 `tpc fragment` + 显式记号 + bytes identity 四例 + `always @(*)` 规则 + dry-run diff；10 单测、真实语料 259 文件 0 变化；`gap-fragment-mode.md`（#70） |
| 4 | **片段模式 P1** | ⏳ `[[island_rules]]` 声明面 + rewriter 能力位 + 多规则/冲突/后验；**契约面需作者批准**（P0 不碰声明面） |
| 5 | **unit graph 内置能力** | ⏳ `unit_graph.v1`：C include 与 Verilog module 同图；`ProjectChecker.check([roots])` 同 API；无语言分支 |
| 6 | **精化基座 graph 化** | ⏳ elaboration 只消费 graph 原子/边；T3 接受项 `inst_sites` 命名关闭 |
| 7 | **增量解析/check** | ⏳ 单函数编辑重解析 ≥5x；增量诊断 = 全量结果；编辑器接口 |
| 8 | **诊断粒度** | ✅ 块内 2 坏语句 → 2 条位置正确 `phase-statement`（#71；父容器粗诊断让位）；`test_c_block_diagnostics.py` |
| 9 | **渲染/注释遗留** | ⏳ #72 调查：LineSuffix 吞 token 根因=flatten；强制 group broken 修 C 但 yaml 往返回归，已回退；需源行感知方案 |
| 10 | **工程化缺口** | ⏳ A/B inproc ✅ #73；C→V→C ✅ #74；yaml 幂等 ✅ #76（零宽块结束符不吞注释，两遍逐字相同）；cp1252、eval_benchmark 待 |
| 11 | **吞吐/基准** | ⏳ fuzz 40→100 iter/s；parser 2.5x；benchmark 阈值进 CI |
| 12 | **0.1.4 收口** | ⏳ 全量/A-B/render/c_acceptance/corpus/文档全绿，发布候选 |

**当前 4 / 12**。基线锚：全量 4377/14、A/B 0/144、render 124/124、c_acceptance 49/0、S=1110、feature 0。

## 下一轮入口（每轮替换，不追加）

- **意图**：块 10 继续——CI cp1252 排练口径（`tools/ci_rehearsal.py` 注入 `PYTHONIOENCODING=cp1252` 后跑通）或 `eval_benchmark` 显式口径登记；随后块 11 吞吐/基准。
- **待验证假设**：cp1252 排练失败集中在未自护脚本输出编码；注入 env + 少量脚本自护可在不改行为下全 PASS。
- **台账**：块 1/2/3/8 ✅；块 9 ⏳（#72 源行感知方案未成）、块 10 ⏳（3/5：#73/#74/#76）；主线 2 当前 4/12；P1 待批准。

## 估算依据（对照锚，可复核）

- 主线 1：9 块（#52 收口）；T1–T3：16 提交（#51–#66，均本地提交）。
- 片段模式草稿 §6：P0 1–2 周量级、P1 语法驱动+插件、P2 安全/组合、P3 增量；新增声明段/能力位属框架级。
- 复现：`git log --oneline -20`、`python tools/structural_score.py --compare`、`python tests/e2e/eval_diag_baseline_c.py`。
