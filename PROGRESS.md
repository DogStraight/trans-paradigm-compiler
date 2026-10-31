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
| 4 | **片段模式 P1** | ✅ 全域岛 / 零声明面 / 无记号（`islands/` 五模块 + `tpc fragment`；ADR-0026）；单测 10、真实语料 12 文件 0 crash/0 non-idem、lint 33/0/0 |
| 5 | **unit graph 内置能力** | ✅ `report.graph`（多入口 ⇒ 多根森林；C include 边 / V 实例化边，kind = 配置数据；`inverse` 反查）+ CLI `tpc check <file>...` 多入参（ADR-0027）；新测试 4、analyzer+preprocessor 738 passed、A/B 0/144、benchmark 53 不变；P2 生产者注册表/自动推 roots 留档 |
| 6 | **精化基座 graph 化** | ⏳ elaboration 只消费 graph 原子/边；T3 接受项 `inst_sites` 命名关闭 |
| 7 | **增量解析/check** | ⏳ 单函数编辑重解析 ≥5x；增量诊断 = 全量结果；编辑器接口 |
| 8 | **诊断粒度** | ✅ 块内 2 坏语句 → 2 条位置正确 `phase-statement`（#71；父容器粗诊断让位）；`test_c_block_diagnostics.py` |
| 9 | **渲染/注释遗留** | ⏳ #72 调查：LineSuffix 吞 token 根因=flatten；强制 group broken 修 C 但 yaml 往返回归，已回退；需源行感知方案 |
| 10 | **工程化缺口** | ✅ A/B inproc #73；C→V→C #74；yaml 幂等 #76；cp1252 排练 #77；benchmark 口径 #79（parse 失败事实码保留 + 语法 lint 不再误排除；verilator 共识 0→53） |
| 11 | **吞吐/基准** | ✅ 实测基线重锚（fuzz 5 → 12 iter/s 单进程 / 32 iter/s 8 worker；配置声明缓存 + parser 表复用）+ **共识下限进 CI**：`benchmark_baseline.json` + `test_benchmark_baseline.py`（verilator 53/18/343；只锚共识下限、缺 oracle 即 skip、解析失败=0）；阶段级 fuzz 留 P2.3 backlog（非阻塞） |
| 12 | **0.1.4 收口** | ⏳ 全量/A-B/render/c_acceptance/corpus/文档全绿，发布候选 |

**当前 8 / 12**。基线锚：A/B 0/144、render 124/124、c_acceptance 49/0、S=1110、
`feature_sites compare` ✓（散点已收敛，基线已刷新）、verilator 共识 53；全量复现 `pytest tests/`
（未通过数记 CHANGELOG 当轮条目）。

## 下一轮入口（每轮替换，不追加）

- **意图**：块 6 精化基座 graph 化——elaboration 只消费 unit graph 的原子/边（不再各插件
  自建文件索引）；T3 接受项 `inst_sites` 命名关闭。块 9（#72 源行感知）按触发条件插入。
- **待验证假设**：`inst_sites` / `module_index` 改由 `graph` 供源后，插件侧语义等价（A/B 逐字节）；
  graph 边不足以表达"跨文件精化原子"时，需在 `unit_graph` 加语言无关边种类而非插件私有索引。
- **台账**：块 1/2/3/4/5/8/10/11 ✅；块 9 ⏳（#72）、6/7 未开工；主线 2 当前 8/12。


## 估算依据（对照锚，可复核）

- 主线 1：9 块（#52 收口）；T1–T3：16 提交（#51–#66，均本地提交）。
- 片段模式草稿 §6：P0 1–2 周量级、P1 语法驱动+插件、P2 安全/组合、P3 增量；新增声明段/能力位属框架级。
- 复现：`git log --oneline -20`、`python tools/structural_score.py --compare`、`python tests/e2e/eval_diag_baseline_c.py`。
