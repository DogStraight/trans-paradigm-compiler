# tools/ — 开发自查工具

> 从 `AGENTS.md` 迁出的工具清单（2026-09-18）。这些工具**不进日常门禁**（多为分钟级或有外部依赖），
> 只在对应场景人工/按需跑；**门禁那几条**（`check_hardcode` / `check_doc_refs` / `check_invariants`）
> 在 `policy/` 下并挂 CI，不在此列。
>
> 基线数据在 `tools/baselines/`；本目录只放**可执行脚本**。

## 快速索引（按问题找工具）

| 我想… | 用这个 |
|---|---|
| 确认"这轮改动有没有零变化/只有预期变化" | `ab_pipeline_compare.py` |
| 算结构性改动收益、判主线是否收口 | `structural_score.py` |
| 看"加一个功能要碰几处" | `feature_sites.py` |
| 查"引擎语义一改，哪些语言包配置要跟着改" | `config_sites.py` |
| 怀疑门禁失灵（门禁还在不在握着东西） | `check_gate_efficacy.py` |
| 找冗余文件/草稿残留/悬空引用 | `scan_redundant.py` |
| 找同构重复的测试用例 | `scan_test_redundancy.py` |
| 查某语言包还差哪些构造没被接受 / 没渲染 | `c_acceptance.py` / `render_coverage.py` |
| 查引擎里还有没有语言知识渗透 | `lang_penetration.py` |
| 判断某个测试是不是"靠语言包声明才成立" | `min_pack_probe.py` |
| 排查"换跑法就变脸"（进程/哈希隔离） | `check_test_isolation.py` |
| 诊断跨语言串味 / 看管线状态 | `dump_pipeline_state.py` |
| 发布前本地排练 CI 全部门禁 | `ci_rehearsal.py` |
| 审计循环跑一轮（出候选、落账、自省） | `audit_cycle.py` |

## 命名约定（一眼看出工具性质）

| 前缀 | 语义 | 能否进 CI |
|---|---|---|
| `check_*` | **门禁式**：非零退出即失败 | 可以 |
| `scan_*` | **只报告**：出候选，不裁决 | 否（人判） |
| `*_coverage` / `*_probe` | **度量**：出数字/基线，`--compare` 增长即失败 | 可作 ratchet |
| `*_compare` | **对拍**：PRE vs POST | 否 |
| `*_sites` | **散点计量**：一处事实在几处登记 | 可作 ratchet |

## 按角色分组

### 1. 门禁与一致性

- `check_gate_efficacy.py` — 门禁有效性抽查（真实事故变异，期望门禁变红）。怀疑门禁失灵时。规程见 `docs/audit_system.md`（D5 维度）。
- `check_macro_coverage.py` — 宏位置透明性量化 + 失败面按 token 类型分布。动宏/预处理器路径时。见 `preprocessor/README.md`。
- `check_test_isolation.py` — 进程级隔离对照（每文件一进程 vs 单进程共享档；`--hashseed-scan N` 再换一维）。排查"换跑法就变脸"。见 `tests/README.md`。
- `check_coverage_delta.py` — 增量覆盖率（只看改动文件，几十秒）。大改收尾看新增行是否被覆盖。
- `ci_rehearsal.py` — **本地排练 `ci.yml` 全部门禁**，输出 PASS·FAIL·**SKIP** 矩阵；**SKIP 与「零步骤」都不算绿**（整体 INCOMPLETE，exit 2）。打 tag 或推送分支前。见 `policy/release-checklist.md` §1。

### 2. 审计循环（`docs/audit_system.md`）

- `audit_cycle.py` — 按维度注册表跑探针、落账（`--ledger`）、记人判结论（`--judgement`）与制度改进候选（`--retro`）。**只收集，不裁决**。
- `scan_redundant.py` — 冗余残留扫描：草稿/临时物、gitignored 大目录、**指向草稿区的悬空引用**。默认 dry-run；`--clean <kind> --yes` 才真删。见 `policy/doc-alignment.md`「删除判据」。
- `scan_test_redundancy.py` — 测试同构冗余扫描（只报告）：同文件/同类内结构相同的测试组 → 参数化候选；标注是否被基线锚定。见 `AGENTS.md`「测试门禁 + 测后决策」。
- `structural_score.py` — 结构欠账分 S（复杂度/规模/重复三分量取超额量）；`--save` 写基线、`--compare` 新增即回归。见 `policy/structural_budget.md`。
- `feature_sites.py` — **功能散点计量**：按功能分族枚举实例，扫出"提及它的文件"并归类；`--save`/`--compare`。判保持记 `baselines/feature_sites_kept.json`、已收敛记 `baselines/feature_sites_converged.json`。见 `docs/gaps/gap-feature-scatter.md`。
- `config_sites.py` — **配置同步点位**：`list` 清单 / `check` 漂移哨兵 / `rename` 逐项替换。见 `policy/engine_config_sync.md`。
  > 与 `feature_sites` 的**划界**：`config_sites` 管"**配置键**在语言包里的同步点位"（含改名写回）；`feature_sites` 管"**功能**在插件/引擎/测试/文档里的登记散点"（含预算与判保持）。对象不同，不合并。
- `lang_penetration.py` — 语言知识渗透探针（**弱信号**）：硬信号=规则/节点名，弱信号=语言对象词作标识符（需人判）。见 `docs/gaps/gap-language-penetration.md`。
  > 与 `check_hardcode` R1–R6 的**划界**：门禁抓**硬约束**（可判定的字面量/路径/具体 token 名）；本工具补门禁**抓不到**的弱信号面，只出候选。

### 3. 度量与对照

- `ab_pipeline_compare.py` — PRE(`git archive HEAD`)/POST(工作树) 对拍：逐输入 diff 诊断/success/error/output；`--expect-changed 0` = 零用户可见变化。**只读**，不写工作树。
- `min_pack_probe.py` — 最小语言包探针（行为面基线）：换迷你包跑引擎测试，记录哪些测试仍绿；`--record` 写 `baselines/min_pack_baseline.json`。**强制串行**（并行结果随 worker 分配漂移）。
- `c_acceptance.py` — C 包接受面扫描：45 条构造逐条试解析，报"进 AST / 空 AST / 词法抛错"。**空洞是无声的**。见 `docs/gaps/gap-language-pack-scope.md`。
- `render_coverage.py` — 渲染覆盖率盘点：哪些规则带 `layout`/`body`。引擎对无布局规则**静默输出空串**。见 `docs/gaps/gap-language-pack-scope.md`。

### 4. 诊断与实验

- `dump_pipeline_state.py` — 管线语言状态转储（共享条目/组件/当前语言；`--pre grammar/c4` 复现"同进程先跑过别的语言"）。诊断跨语言串味。
- `bifrost_probe/` — 外部审计 Bifrost 的有效性抽查探针（刻意含坏味，`bifrost scan tools/bifrost_probe` 应报 5 条）。见 `policy/bifrost_audit.md`。

### 5. 基线数据（`tools/baselines/`）

只读数据，由上述工具 `--save`/`--record` 生成，**不要手改**：

| 文件 | 生成者 | 被谁守 |
|---|---|---|
| `structural_baseline.json` / `structural_kept.json` | `structural_score.py` | `tests/policy/test_structural_kept.py` |
| `feature_sites_baseline.json` / `_converged.json` / `_kept.json` | `feature_sites.py` | `tests/policy/test_feature_sites.py` |
| `min_pack_baseline.json` | `min_pack_probe.py --record` | `min_pack_probe.py`（比对即 exit 1） |

## 非本目录的按需门禁

- **fuzz 回馈链路**：`tests/fuzz/run_fuzz.py` 找、`tests/fuzz/shrink.py` 缩与沉淀、`tests/edge/run_edge.py` 门禁。见 `tests/fuzz/README.md`。
- 真实语料误报基线：`tests/e2e/eval_diag_baseline.py`（增长即失败）。
- 弱断言比例 ratchet：`tests/policy/test_assert_strength.py`。
- 外部审计 Bifrost（结构面信号）：`policy/bifrost_audit.md`。
