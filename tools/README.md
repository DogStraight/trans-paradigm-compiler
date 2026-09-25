# tools/ — 开发自查工具（按需/人工跑，都不进日常门禁）

> 从 `AGENTS.md` 迁出的工具清单（2026-09-18）：命令与清单落就近 README，
> `AGENTS.md` 只留一行指针。这些工具**不进日常门禁**（多为分钟级或有外部依赖），
> 只在对应场景人工/按需跑。

| 工具 | 用途 | 何时跑 | 规程/判据 |
|------|------|--------|-----------|
| `config_sites.py` | 机械枚举语言包配置点位：`list` 清单 / `check` 漂移哨兵 / `rename` 逐项替换 | 引擎语义/键名变更时 | `policy/engine_config_sync.md` |
| `check_coverage_delta.py` | 增量覆盖率（只看改动文件，几十秒） | 大改收尾看新增行是否被覆盖 | — |
| `check_gate_efficacy.py` | 门禁有效性抽查（真实事故变异，期望门禁变红） | 怀疑门禁失灵时 | — |
| `check_test_isolation.py` | 进程级隔离对照（每文件一进程 vs 单进程共享档；`--hashseed-scan N` 再换一维 PYTHONHASHSEED） | 排查"换跑法就变脸" | `tests/README.md` |
| `dump_pipeline_state.py` | 管线语言状态转储（共享条目/组件/当前语言；`--pre grammar/c4` 复现"同进程先跑过别的语言"） | 诊断跨语言串味 | — |
| `check_macro_coverage.py` | 宏位置透明性量化 + 失败面按 token 类型分布 | 动宏/预处理器相关路径 | ADR-0017（边界依据） |
| `bifrost_probe/` | 外部审计 Bifrost 的有效性抽查探针（刻意含坏味，`bifrost scan tools/bifrost_probe` 应报 5 条） | 接外部审计或怀疑其失效时 | `policy/bifrost_audit.md` |
| `structural_score.py` | 结构欠账分 S（复杂度/规模/重复三分量取**超额量**；`--save` 写基线、`--compare` 新增即回归） | 结构性改动前后算收益 / 判主线是否收口 | `policy/structural_budget.md`（口径 R1–R6 与停止判据；判保持登记在 `structural_kept.json`） |
| `feature_sites.py` | **功能散点计量（接触点清单 + 预算）**：按功能分族（加检查规则/语法构造/能力位/配置键）枚举现存实例，扫出"提及它的文件"并按角色归类（插件内 / 引擎侧登记 / 行为基线 / 测试 / 文档）；`list` 清单、`--save` 写基线、`--compare` 散点增长即 exit 1。判据不是"文件多"而是**同一事实被写在 ≥2 个必须手工同步的位置**（测试/文档不计欠账）；判保持记 `feature_sites_kept.json`、**已收敛**（不再靠人记着同步：单一来源派生或门禁校验）记 `feature_sites_converged.json`——两者都须 reason+source，门禁 `tests/policy/test_feature_sites.py` 守（含反向防滥用：路径/source 门禁须真实存在、不得空转登记） | 动插件登记面/基线/词汇表前后对照；判"该合并哪几处" | `docs/gaps/gap-feature-scatter.md`（口径与拆步；基线 `tools/feature_sites_baseline.json`） |
| `lang_penetration.py` | 语言知识渗透探针（弱信号）：引擎里出现语言包规则/节点名（硬信号）+ 语言对象词作标识符（弱信号，需人工判） | L1 渗透复审 / 动 analyzer 语义面前后对照 | `docs/gaps/gap-language-penetration.md`（三条判据与实测清单） |
| `min_pack_probe.py` | **最小语言包探针（行为面基线）**：把默认语言包换成迷你包跑引擎测试，记录"哪些引擎测试仍绿"（仍绿 = 引擎通用面）；`--record` 写基线，默认比对并「有回归即 exit 1」。机制 = `$TPC_CONFIG` 指向临时配置（**零引擎改动**）。⚠ **强制串行**（默认补 `-n 0`）——探针故意混跑双语，并行结果随 worker 分配漂移，不可作判据 | 动精化基座 / analyzer 语义面前后对照（ADR-0019 P2–P3）；判"某测试是不是靠语言包声明才成立" | `docs/gaps/gap-language-penetration.md` 判据 1；基线 `tools/min_pack_baseline.json`（与探针包绑定，换包须重记；**必须串行重记**） |

另有非本目录的按需门禁：

- 真实语料误报基线：`tests/e2e/eval_diag_baseline.py`（**增长即失败**；查证误报用
  `tests/e2e/eval_benchmark.py`，需外部 oracle）
- 外部审计 Bifrost（Python 侧结构面信号：影响面/到达测试、复杂度、异常吞吃、结构
  重复、死代码、弱断言、结构查询）：`policy/bifrost_audit.md`
