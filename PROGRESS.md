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
| 1 | **基线清算** | ⏳ 删 TODO 过期三条（结构/散点/性能措辞）；`structural_score --compare` Δ0、`feature_sites` 0、`config_sites check` PASS |
| 2 | **parser 性能收口** | ⏳ cJSON 单文件 ≤5s；C 语料门禁 ≤30s；A/B 0/144；corpus 7/7 0 诊断 |
| 3 | **片段模式 P0** | ⏳ 独立 CLI + 显式记号 + bytes identity（LF/CRLF/BOM/无尾）+ 一条真实规则 + dry-run diff + falsification 记录；设计输入 `_drafts/marker-mode-evaluation.md`（未入库） |
| 4 | **片段模式 P1** | ⏳ `[[island_rules]]` 声明面 + rewriter 能力位 + 多规则/冲突/后验；**契约面需作者批准**（P0 不碰声明面） |
| 5 | **unit graph 内置能力** | ⏳ `unit_graph.v1`：C include 与 Verilog module 同图；`ProjectChecker.check([roots])` 同 API；无语言分支 |
| 6 | **精化基座 graph 化** | ⏳ elaboration 只消费 graph 原子/边；T3 接受项 `inst_sites` 命名关闭 |
| 7 | **增量解析/check** | ⏳ 单函数编辑重解析 ≥5x；增量诊断 = 全量结果；编辑器接口 |
| 8 | **诊断粒度** | ⏳ 块内 N 个坏语句 → N 条位置正确诊断 |
| 9 | **渲染/注释遗留** | ⏳ LineSuffix/注释簿记/括号首元素三形态幂等且保真 |
| 10 | **工程化缺口** | ⏳ A/B inproc、yaml workflow 幂等、cp1252 排练、C→V→C postpass、eval_benchmark 口径 |
| 11 | **吞吐/基准** | ⏳ fuzz 40→100 iter/s；parser 2.5x；benchmark 阈值进 CI |
| 12 | **0.1.4 收口** | ⏳ 全量/A-B/render/c_acceptance/corpus/文档全绿，发布候选 |

**当前 0 / 12**。基线锚：全量 4377/14、A/B 0/144、render 124/124、c_acceptance 49/0、S=1110、feature 0。

## 下一轮入口（每轮替换，不追加）

- **意图**：块 1 基线清算——删/改写 TODO 三条过期项（结构欠账/散点新增/性能前提），重跑三探针；随后块 2 性能测量轮（取基线 + profiling 定位，不直接改代码）。
- **待验证假设**：过期项确由 T3-① #60 刷新与 T1 实验回退导致；三探针仍 Δ0/0/PASS；cJSON 回溯热点可稳定复现并给出定位证据。
- **台账**：主线 1 + T1–T3 已收口；新刻度 12 块、当前 0/12；片段模式草稿已定位（`_drafts/marker-mode-evaluation.md`，未入库；P0 只做独立原型，P1 契约面待批准）。

## 估算依据（对照锚，可复核）

- 主线 1：9 块（#52 收口）；T1–T3：16 提交（#51–#66，均本地提交）。
- 片段模式草稿 §6：P0 1–2 周量级、P1 语法驱动+插件、P2 安全/组合、P3 增量；新增声明段/能力位属框架级。
- 复现：`git log --oneline -20`、`python tools/structural_score.py --compare`、`python tests/e2e/eval_diag_baseline_c.py`。
