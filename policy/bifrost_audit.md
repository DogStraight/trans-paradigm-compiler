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

## 重构期用法（能力族 ④ 变更差分，2026-09-22 接入）

> 动机：结构性重构（移文件 / 拆类 / 改签名）**行为面证据对它无感**——pytest 全绿、
> 字节对拍一致、诊断基线不变，都不能说明"搬对了、没搬脏"。④ 补的正是这一面。

```powershell
# 重构前后各跑一次（锚点 = 重构前提交）
bifrost --root . --tool score_diff     --args '{"base":"<锚点>","target":"HEAD"}'
bifrost --root . --tool blast_radius   --args '{"base":"<锚点>","target":"HEAD"}'
bifrost --root . --tool missing_tests  --args '{"base":"<锚点>","target":"HEAD"}'
python tools/structural_score.py --compare     # 结构欠账分（新增即回归，退出码 1）
```

- `score_diff` 字段口径：`geometry`（ins/del/introduced/deleted/moved/signature_changes/
  directories_changed/mean_directory_distance）、`baseline`（`cognitive_before/after/delta`）、
  `verification.untested_fraction` + `without_direct_test_reference`（改了却无直接测试
  引用的生产符号，逐条带 `non_test_reference_sites`）、
  `coordination.external_callers_by_signature_change`（签名变更的**外部**调用点——
  **改接口前先看它**）。
- ⚠ `excluded.unparseable_files` 把 `.md` / `.toml` 记为不可解析（本仓 21 个）——
  属预期，不是错误。
- ⚠ **两个基线口径不同，别混用**：`structural_score.py --save/--compare` 是**键级**
  基线（符号全名的路径键）→ 移文件会让旧键"消除"、新键"新增"；故**跨搬家窗口看
  `score_diff` 的聚合量**，`--compare` 用于**同布局内**的回归。

**当前锚点（精化基座重构前，2026-09-22）**：提交 `c63c6bb`，S=0 已冻结于
`tools/structural_baseline.json`。同窗口实测（`HEAD~10..HEAD`）：认知 Δ **−23**、
ins 1143 / del 598、introduced 48 / deleted 17 / moved 69 / signature_changes 36、
`untested_fraction` **0.9**（91/233 改动生产符号的 90% 无直接测试引用——本仓测试是
行为面/语料驱动，非逐符号，属预期画像；**重构后该值若显著上升才是信号**）。

## 能力族清单与本仓实测状态（2026-09-20）

按"信号类型"分类；"本仓状态"以实测为准（用时 = 本机一次调用实测）。

| 族 | 工具 / 策略 | 本仓状态 | 值得注意的点 |
|---|---|---|---|
| **① 规模与复杂度** | `compute_cyclomatic_complexity`（10）、`compute_cognitive_complexity`（15）、`report_long_method_and_god_object_smells` | **已逐项收口**：CC/认知 19 项 + 类/模块规模 4 项均下结论（前 17 项 = 分派型/单一职责循环，后 4 项 = **最大单方法认知 10–14、规模来自方法数**的低认知大容器）；函数级 >80 行 = 0。判据与证据表见 `structural_budget.md` 六节 | ⚠ 长方法/上帝对象工具**每调用最多分析 25 个文件**（`Files analyzed cap: 25`，**不报截断**）→ 分块 ≤20；CC/认知两工具**无上限** |
| **② 结构重复** | `report_structural_clone_smells`（minTokens=12 / shingleSize=2 / minShared=3 / astThreshold=70） | 已用，**该族已闭合**：真重复 2 处合并（常量表达式解析器 → `_IntExprParser`；两形态字段读取 → `_node_utils.dual_get`）、3 对逐行对照后判保持，D 超额 **940 → 0**。快照按 R3/R6 口径重测（同参数现报 108 对原始命中，过滤后 0） | 无上限提示，但分块大小会改变"最佳克隆对"选取（36 文件一次 46 条 vs 18+18 两次 52 条）→ 对数须固定分块比较 |
| **③ 异常与断言** | `report_exception_handling_smells`（权重打分）、`report_test_assertion_smells` | 已用并收口（吞吃 44/44、断言 22/22 判定） | 断言族在本仓全是"断言在调用链内"的形态假阳性；断言工具整仓单次会截断（337 文件只报 8 条）→ 分块 |
| **④ 变更差分** | `score_diff`、`missing_tests`、`blast_radius` | **已接入流程**（重构期必跑；2026-09-22 实测：`blast_radius` 2.4s、`missing_tests` 0.1s、`score_diff` 44.1s / 10 提交窗口） | **唯一补"结构面证据"的族**：`score_diff` 给结构面净变化（认知 Δ / 增删行 / 引入符号 / 签名变更 / `untested_fraction` / 未解析使用点），`missing_tests` 给"改动未达测试"的函数计数——本仓现有三道证据（pytest、字节对拍、诊断基线）全是**行为面**，对"移文件 / 拆类 / 改签名"无感。用法见下节 |
| **⑤ 热点交叉** | `analyze_git_hotspots` | **未用**（本轮实测 3.3s，278 commits） | 给 churn × complexity 表：本仓 top 为 `analyzer/structure.py`(29/10)、`pipeline/__init__.py`(26/10)、`preprocessor/_expand.py`(21/7)——**正是超长函数所在文件**，可作"先动哪个"的经验依据 |
| **⑥ 注释密度** | `report_comment_density_for_files` / `_for_code_unit` | **未取**（本轮实测 1.0s 可用） | 输出 Hdr/Inl/Span 计数；本仓注释密度偏高，纯比例意义有限，只宜当"异常低"的筛子 |
| **⑦ 死代码** | `report_dead_code_and_unused_abstraction_smells` | **不可用** | 只支持 Rust → Python 侧无此信号；本仓等价面 = Pylance 诊断 + `policy/pylance-cleanup.md` |
| **⑧ 安全/密钥** | `report_secret_like_code`、`security.java.*` 策略 | **不可用** | `secret_like_code` 在本仓**直接 panic**（Rust 非 ASCII char boundary，遇中文即崩，2026-09-20 实测）；Java taint 策略不适用（仓内无 Java）。开源前检查改用其它手段 |
| **⑨ 内置策略（19 条）** | code-smells 17 + security 2 | 已分类（Python 有效面 12 条） | Python 相关：`dynamic-evaluation`（已修）、`unsafe-deserialization`（0 命中）、`python-absent-member`（**结论缺失**，需整仓跑 1h+，缩范围必 `inconclusive`）、in-loop 族（已判"形态 vs 病理"）。Go 3 / Rust 2 / Java 2 空跑 |
| **⑩ 结构查询** | `--query-file`（RQL）/ `--repl` / `--list-row-schemas` | **未用** | 能答**跨维度**问题（如"CC>10 且被 ≥3 处调用"、"哪些引擎模块导入了 `grammar/`"——后者正是本仓"语言知识不进代码"硬约束的可机器化面）。写查询前先读 `--list-row-schemas` 的行域/字段目录 |
| **⑪ 集成面** | `--mcp symbol\|extended`（含 `query_code`）、`--lsp`、`run_policy`（MCP Tasks） | **未用** | 把"外部裁判"从人工 CLI 变成 agent 可调用能力；给 agent 的推荐面是 `symbol\|extended` |

**优先级建议**（按"对本仓缺口的边际价值"）：④ > ⑤ > ⑩ > ⑪ > ⑥ > ⑨（absent-member）。
④ 直接补"结构面证据"；⑤ 决定 17 个类与 5 个长函数的动手顺序；⑩ 能机器化本仓的硬约束自查。

**收尾归属判定（2026-09-22，审计线收口时定）**：

| 族 | 归属 | 理由 |
|---|---|---|
| ④ 变更差分 | **纳入流程**（重构期必跑） | 唯一补"结构面证据"的族，见上「重构期用法」节 |
| ⑤ `analyze_git_hotspots` | **按需** | 只在决定"先动哪个"时跑一次；本仓 churn × complexity 表已落 `structural_budget.md` 五节 |
| ⑥ 注释密度 | **不纳入** | 本仓注释密度整体偏高，"比例"意义有限，只宜当"异常低"的筛子 |
| ⑩ RQL（`--query-file`） | **按需** | 答**跨维度**问题的手段（如"哪些引擎模块导入了 `grammar/`"= 硬约束可机器化面），不是每轮要跑的门禁 |
| ⑪ MCP / LSP | **按需** | agent 集成面（把外部裁判变成可调用能力），需求驱动再启 |

> **命中 ≠ 待办**：本工具族按**阈值**报命中，阈值附近会无穷再生。哪些命中算
> "必须处理"、一次改动值多少、何时收口，由 `structural_budget.md` 定（超额量口径
> R1–R5 + 结构欠账分 S + ROI 门限），度量用 `tools/structural_score.py`。

## 判据集（跨项复用，2026-09-22 收口时固化）

> 逐项理由（"这一条为什么保持"）落在 `tools/structural_kept.json`（可回滚、可 diff）；
> 本节只留**决定"下一个同类命中怎么判"的判据**——没有它们，审计每轮都要重新论证。

| 族 | 判据 | 本仓结论 |
|---|---|---|
| **CC / 认知过阈** | ① *分派型*：一类型/一 Doc 变体一臂、臂内无逻辑（纯递归/纯取值/纯重建）→ **保持**——CC 高只因变体多，拆开把同一语义散成 N 个函数，可读性反向；② *有内部逻辑*：臂内含嵌套循环/多重条件/可提重复模式 → **拆**；③ `tools/*` 一次性命令行扫描 → 低优先（非产品路径） | 过阈项**全部**落在 ①（② 已拆完）→ 停止线在"每项有结论"，不在"数字归零" |
| **性能类 in-loop**（`performance.*-in-loop`） | **同一文件是否被同一次运行反复读**：是 → 修；每文件各读一次 → 保持（命中的是**形态**不是病理） | 12 处：1 处真问题（`ModuleIndexer` 目录兜底对每个未解析单元名重读整目录 → 改"按目录建一次单元名→文件索引" + 诱饵计数回归测试），11 处保持；`tools/bifrost_probe/smelly.py` 是**刻意坏味探针**——修好即门禁失效，不得"修" |
| **测试断言族** | 信号来自"断言不在被测函数体内"的**词法**判据；本仓断言多在被调用的助手 / 自带 `_assert_*` / `raise` 校验内 | **22/22 判保持**（无语义问题）；按此判据，新命中**先查调用链再判**，别直接当"弱断言" |
| **结构重复**（`report_structural_clone_smells`） | 见 `policy/structural_budget.md` R3（>40 tok **且**两侧非薄入口 **且**不都在 `policy/`）：入口样板的相似度全在装饰器/签名/docstring 上，判据是"**是否还有未共享的逻辑**"故按**体形态**判，不按 token 数判 | 快照归位结果见 `structural_budget.md` 六节「B-C 快照归位」 |

## 已知边界（实测）

- 子目录当 root → 声明面不全（`inconclusive`），别据此下"干净"结论。
- 路径字段是**相对扫描 root** 的（`scan preprocessor` 时 `primary.path` = `_expand.py`）。
- 不做路径可行性 / 全程序 points-to / 通用别名集；动态候选（本仓的动态装载、属性注入、
  插件注册）会落 `unproven`，需按候选而非结论对待。
- 动态求值策略对 `eval/exec` 报 warning 级——本仓 `preprocessor` 侧无命中，仓内
  `declare_cfg` 走的是模块属性注入，不触发。
