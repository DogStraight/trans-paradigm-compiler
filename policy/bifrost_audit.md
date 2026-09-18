# Bifrost 外部审计规程（按需/人工跑，不进日常门禁）

> 定位：**外部裁判**（Brokk 的静态分析工具箱，Apache-2.0 开放核心，Rust）。
> 仓内门禁管"行为正确性与一致性"（测试 / 真实语料对拍 / 诊断基线 / 隔离档）；
> Bifrost 管**结构面信号**：改动影响面、到达的测试、循环内昂贵操作、异常吞吃、
> 长方法与上帝对象、结构重复、死代码/一次性抽象、测试断言薄弱、注释密度、
> git 热点、密钥样码。**只覆盖 Python 侧**——Verilog/TOML 不在其支持语言内，
> `grammar/**` 仍归仓内自查面（`policy/check_*` + 专项工具）。
> 实测日期：2026-09-18（本机 Windows，bifrost 0.11.4）。

## 装与验

```powershell
uv tool install brokk-bifrost   # 隔离安装（Windows 有预编译 wheel，约 53 MiB）
bifrost --version               # → 版本 + 内置策略包清单（code-smells / security）
```

## 先小后大（耗时实测）

| 跑法 | 命令 | 实测耗时 | 结论可信度 |
|------|------|---------|-----------|
| 单文件/极小目录 | `bifrost scan <dir>` | 1.8s（1 文件探针） | 完备 |
| 组件当 root | `bifrost scan preprocessor` | 15.7s（13 文件） | ⚠ 声明面不全 |
| 仓库 root + 限定范围 | `bifrost --policy --root . --sources preprocessor` | 35.7s | 全部 `complete` |
| 单次工具 | `bifrost --root . --tool <name> --args '{…}'` | 2.4s / 4.2s | 看该工具自述边界 |
| 全仓 | `bifrost scan .` | 未实测（分钟级） | — |

**规则**：快验用 `--tool` 单次调用或 `scan <小目录>`；要**完备结论**必须保留仓库为
root（`--policy --root . --sources <子集>`）。实测差异：子目录当 root 时
`bifrost.correctness.python-absent-member` 报 `inconclusive`
（`capability_incomplete` + "requires an active Python declaration surface"）——
声明面/引用图按 root 构建，缩 root 会丢跨文件事实。

## 三种用法

### 1) 零配置策略扫描（19 条内置策略）

```powershell
bifrost scan <PATH> --format json --fail-on never --output out.json
```

读报告的顺序（**零结果 ≠ 干净**）：

- `runs[].completion.type`：`complete` / `inconclusive`（后者先看 `diagnostics`）
- `runs[].diagnostics`：`empty_selection`（选择器在本工作区没绑到端点，advisory，正常）/
  `capability_incomplete`（能力不足，结论不可用）
- `runs[].findings[]`：`{id, identity_stability, policy_id, policy_hash, severity,
  certainty, completeness, primary:{path,region}, evidence}`
- `runs[].work.scanned_files`：该策略实际扫到的文件数（非 Python 策略在本仓为 0）

本仓噪声画像：19 条里 Go/Rust/Java 专属约 8 条空跑；Java taint 两条给
`empty_selection` 提示；Python 侧 11 条有效。`identity_stability: strong` 的 finding
可做 baseline/抑制（`--policy-file` / `.bifrost/suppressions.json`）。

### 2) 单次工具（大改收尾自检最常用）

```powershell
# 改动影响面 + 到达的测试（默认比 HEAD vs 工作区；显式端点用 base/target）
bifrost --root . --tool blast_radius --args '{"base":"HEAD~5","target":"HEAD"}'
bifrost --root . --tool missing_tests  --args '{"base":"HEAD~5","target":"HEAD"}'
bifrost --root . --tool score_diff     --args '{"base":"HEAD~5","target":"HEAD"}'

# 结构查询（RQL）/ 交互 / 策略选择
bifrost --root . --query-file q.rql
bifrost --root . --repl
bifrost --list-policies ; bifrost --policy --policy-file <p.rqlp>
```

`blast_radius` 结果字段：`test_scopes` / `changed_callables` /
`analysis.analyzer_changed_test_paths` / `analysis.paths_outside_file_graph` /
`analysis.graph_completion`。**零到达测试不构成"无需验证"**：先看
`paths_outside_file_graph`（构建/数据/文档类改动本就不在文件依赖图里）。

slopcop 诊断族（**本地就有**，托管 SlopCop 的服务端工具层即此）：

```powershell
bifrost --root . --tool report_exception_handling_smells --args '{"file_paths":["main.py"]}'
# 同族：report_long_method_and_god_object_smells / report_structural_clone_smells /
#       report_dead_code_and_unused_abstraction_smells / report_test_assertion_smells /
#       report_comment_density_for_files / report_comment_density_for_code_unit /
#       analyze_git_hotspots / report_secret_like_code /
#       compute_cyclomatic_complexity / compute_cognitive_complexity
```

其中 `report_exception_handling_smells` 按"权重打分"排序（宽 catch 类型 / 空体 /
仅注释体 / 仅日志体加分，有实质语句减分），可用 `min_score` 与各权重调精度。
需要文件清单（`file_paths` 必填），批量时用脚本生成列表。

### 3) MCP（给 agent 的反馈链路）

stdio + 显式 root（JSON 宿主配置）：

```json
{"mcpServers":{"bifrost":{"command":"bifrost",
  "args":["--root","<绝对路径>","--mcp","symbol|extended"]}}}
```

- 工具集：`symbol` / `workspace` / `diff` / `extended` / `text` / `slopcop`；
  `core` = `symbol|workspace|diff`；`searchtools` = 全部（无参启动的默认）。
  给 agent 的推荐面：`symbol|extended`（含 `query_code`；`slopcop|diff` 是审计面）。
- MCP 单请求预算默认 5s（`BIFROST_MCP_REQUEST_BUDGET_SECS` 5–60）；`run_policy` 走 MCP Tasks。
- 生效校验要分开做：工具出现（`tools/list`）≠ 工作区已绑定 ≠ 单个工具可用。
  用"只在当前工作区存在的声明"做一次符号调用，并核对返回的是项目相对路径。

## 本仓怎么用

- **何时跑**：大改收尾（重构 / 删路径 / 改签名 / 动架构不变量）后自检；定期换外部裁判
  做对照；怀疑门禁失灵时抽查。
- **问什么**：结构面与影响面（"这次改动到达哪些测试"、"引擎侧还有哪些吞异常的兜底"、
  "哪两段结构重复"、"哪个函数已超复杂度阈值"）。
- **不问什么**：Verilog 规则正确性、语言知识是否漏进引擎——那是仓内面
  （`policy/check_hardcode.py`、`tools/config_sites.py`、`tools/check_macro_coverage.py`）。
- **有效性抽查**：`bifrost scan tools/bifrost_probe` 应报出 5 条——1 条 warning
  （`dynamic-evaluation`）+ 4 条 note（循环内 file-read / parsing / regex-compile /
  subprocess），实测 2026-09-18 命中且无多余命中。报不出说明工具或策略面失效——
  与 `tools/check_gate_efficacy.py` 同思路（真实事故变异期望变红）。
- exit code：0 干净 / 1 有 finding / 2 结论不可用（含 `inconclusive`）。小目录扫描
  会同时带 `inconclusive` 提示（见上表"组件当 root"），判读以
  `runs[].completion` + `runs[].diagnostics` 为准，不看 exit code 一个数。
- **落档**：审计结论按"落档分流"走（行为预期→测试断言；边界→`docs/gaps/`；
  用户可见变化→CHANGELOG），不写进本文件。
- **不进日常门禁**：需要外部二进制，且全量扫描是 30s–分钟级。

## 已知边界（实测）

- 子目录当 root → 声明面不全（`inconclusive`），别据此下"干净"结论。
- 路径字段是**相对扫描 root** 的（`scan preprocessor` 时 `primary.path` = `_expand.py`）。
- 不做路径可行性 / 全程序 points-to / 通用别名集；动态候选（本仓的动态装载、属性注入、
  插件注册）会落 `unproven`，需按候选而非结论对待。
- 动态求值策略对 `eval/exec` 报 warning 级——本仓 `preprocessor` 侧无命中，仓内
  `declare_cfg` 走的是模块属性注入，不触发。
