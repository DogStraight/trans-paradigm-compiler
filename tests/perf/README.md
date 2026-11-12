# tests/perf — 性能基线 + ratchet（0.1.5 块 1）

> 目的：给 0.1.5 的性能优化块（语义层构建、增量 check）一个**可复核的度量底座**，
> 让"优化收益/回归"在仓内有唯一口径，而不是散落在 CHANGELOG 的一次性数字里。
> 口径来源：`docs/gaps/gap-semantic-performance.md`（2026-11-12 实测：check 的
> elaborate 占 42–61%、parse 23–39%，format 的 parse 约 86%）。

## 场景（真实入口 + 仓内真实语料）

| 场景 | 入口 | 语料 |
|---|---|---|
| `tv80_check` | `ProjectChecker.check` | `tests/e2e/samples/real/ref/ref_tv80_core.v` |
| `picorv32_check` | 同上 | `.../ref_picorv32.v` |
| `tv80_format` | `python main.py format`（真实 CLI 子进程） | `ref_tv80_core.v` |
| `crc32_check` | `ProjectChecker.check`（`grammar/c` + 语料 include 面） | `tests/e2e/samples/real_c_ref/ref/crc32.c` |

## 为什么会跨机器可比

每次运行同时测一个**校准微基准**（`_calibration_work`，固定循环），场景记录
`ratio = 场景秒 / 校准秒`；基线存 ratio 而不是绝对秒。硬件/解释器整体快慢被约掉，
夜间 ubuntu runner 与本地机器可同一套阈值比较（仍以本地为权威复核）。

## 判据（ratchet）

- `--save`：每场景 1 次预热 + `--reps`（默认 3）取中位数；**任一场 CV >10% 拒绝录制**
  （先稳定环境/重跑，不把噪声立成基线）。
- `--compare`（夜间 + 本地）：场景集合变化（新增/消失）⇒ **exit 1**；ratio 劣化 >10% ⇒
  **exit 1**；基线缺失/结构不合法 ⇒ **exit 2**；本次测量 CV >10% 只告警（median 仍参与对比）。
- 优化变快不红（ratchet 只防回归）；场景增删必须同一次提交改基线。
- **不放进 PR CI**（计时噪声会假红）；入口在 `.github/workflows/nightly.yml`，本地发布前/
  性能块收口手动跑。

## 命令

```powershell
python tests/perf/run_perf.py --list-scenarios
python tests/perf/run_perf.py --save            # 录制/更新基线（要求稳定；约 3–4 分钟）
python tests/perf/run_perf.py --compare         # ratchet（约 3–4 分钟）
python tests/perf/run_perf.py --check-baseline  # 只校验基线结构（秒级）
```

基线：`tools/baselines/perf_baseline.json`（含 machine/python 信息、tolerance、CV 上限）。
本地基线以本机录制为准；夜间 runner 若非基线机器，比较仍按 ratio 口径执行。

## 关联

- `docs/gaps/gap-semantic-performance.md`（为什么是这些场景/占比）
- `PROGRESS.md` 0.1.5 块 1；`tests/policy/test_perf_baseline.py`（结构/比较逻辑判据）
- 性能块 2/3 的收益直接看本档 `--compare` 表的 ratio 变化（**改前红 → 改后绿**）
