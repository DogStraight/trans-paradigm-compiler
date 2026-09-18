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

另有非本目录的按需门禁：

- 真实语料误报基线：`tests/e2e/eval_diag_baseline.py`（**增长即失败**；查证误报用
  `tests/e2e/eval_benchmark.py`，需外部 oracle）
- 外部审计 Bifrost（Python 侧结构面信号：影响面/到达测试、复杂度、异常吞吃、结构
  重复、死代码、弱断言、结构查询）：`policy/bifrost_audit.md`
