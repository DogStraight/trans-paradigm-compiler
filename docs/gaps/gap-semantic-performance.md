# Gap — 语义层性能（check 耗时结构 / 优化方向）

- 状态：**已测量（2026-11-12，0.1.5 调研）**——本档记测量口径、结构与候选方向；
  优化**未立项**（作者定 0.1.5 范围后再开）
- 关联：`ROADMAP.md` P2.3（验证吞吐）/ P3.4（增量 check）/ P3.5（PyO3）；
  `gap-verification-engineering.md`（吞吐边界与增量边界）
- 参照：`policies/` 无关；口径 = 单次运行墙钟 + cProfile 相对占比（后者有 profiler 放大，
  只用于定位热点，不用于声称绝对加速）

## 测量口径（可复核）

| 项 | 值 |
|---|---|
| 输入 | `tests/e2e/samples/real/ref/ref_tv80_core.v`（169,628 字符 → 展开 170,327；22,604 tokens；127 顶层单元）；`ref_picorv32.v`（94,663 字符） |
| 入口 | `ProjectChecker(rules_dir="grammar/verilog", ext_dirs=[]).check([file])`；format = `python main.py format <file>` |
| 本机 | Windows / Python 3.14（`D:\Python\python.exe`） |
| 脚本 | `.scratch/research_015/profile_pipeline.py` / `profile_phases.py`（一次性，不入库） |

## 阶段墙钟（单入口，单位秒）

| 阶段 | tv80 | 占 check | picorv32 | 占 check |
|---|---|---|---|---|
| discover + parse | 6.83 | **22.6%** | 5.52 | **39.0%** |
| elaborate（精化/信号图） | 18.32 | **60.6%** | 5.92 | **42.0%** |
| analyze（postpass） | 2.75 | 9.1% | 2.70 | 19.1% |
| collect | 0.01 | ~0 | 0.01 | ~0 |
| **check 合计** | **30.25** | 100% | **14.15** | 100% |

format（tv80，CLI 含进程启动）：**14.59s** ≈ 宏展开 0.82 + 词法 0.40 + parse 12.48 +
渲染 ~0.9 ⇒ **parse 约占 format 的 86%**。

## 热点（cProfile，tv80 check，profiled 100.4s，仅相对）

- `_elaborate` **65.9s**（66%）：`solve_signal_graph` **63.7s** → `_sg_connections` 60.4 →
  `_sg_named_connection` 60.4 → `_sg_emit_penetrated` 60.4 → `_resolve_port_drivers` 60.4 →
  `_port_driver_sources` 60.4 → **`_port_src_from_procs` 47.4s（60 次调用）**。
- 通用树/渲染开销：`core.define.iter_children` **3,320,483 次调用**（tottime 15.7s）、
  `iter_nodes` 1,317,596 次（tottime 3.5s）；`render_subtree`/`Renderer.render` **41,288 次**
  （累计 34.1s；`_graph._render` 每目标一次）。
- `_discover_all` 23.6s（24%，解析/发现）。

## 机制结论（为什么这么慢/哪里可省）

1. **端口驱动源是 per-port 全树扫描**：`_port_driver_sources` 按 `(module, port)` 缓存，
   但每个 port 仍调 `_port_src_from_procs` / `_port_src_from_assigns` 扫**整个单元子树**、
   且对每个赋值节点 `_render(target)` 后与 port 比较 ⇒ 成本 ≈ O(端口数 × 单元节点数)。
   单遍 per-module 建 `{signal → sources}` 索引可把乘数降为 1（预期 elaborate 大降，需实测）。
2. **渲染未按节点身份复用**：同一目标节点在多次端口求解中反复 render。
3. **树遍历走生成器且每层重建**：`iter_children` 3.3M 次调用是纯 Python 开销大头之一。
4. **增量 check 的天花板**：现有解析层增量只能省 discover+parse（tv80 22.6% / picorv32 39%）；
   要"编辑→亚秒反馈"必须攻语义层（elaborate），所以 P3.4 的语义失效模型是核心，不是可选。

## 0.1.5 候选方向（未实施；先证后改）

| # | 方向 | 预期待办 | 判据（要能红） | 止损 |
|---|---|---|---|---|
| 1 | 端口源单遍索引（语言包 `_graph.py`） | 消除 per-port 全树扫描 | 诊断逐字节相等 + tv80 check 降 ≥20% | <10% 即放弃并落档 |
| 2 | 渲染 memo（按 `id(node)`，随求解器生命周期） | 41k 次渲染 → 显著下降 | 同上 + 渲染调用数记录 | 缓存命中 <50% 放弃 |
| 3 | 树遍历优化（`core.define.iter_children/iter_nodes`） | 削生成器开销 | 微基准 ≥30% 且全量回归绿 | 引入子节点缓存后语义风险 → 停止 |
| 4 | 增量 check 切片 0（warm + 解析层增量 + **全量**语义） | 先测上限（仅省 parse） | tv80 ≥1.3x / picorv32 ≥1.5x 才继续 | 低于阈值 → 直接转语义失效模型 |
| 5 | 性能常驻测试面（`tests/perf/` + 基线 ratchet） | 把本档口径变成门禁 | 基线外新增即红；CI/nightly 有入口 | 无 |

## PyO3（P3.5）判据（本档结论：暂缓）

- **格式路径** parse 占 86% ⇒ PyO3 潜在收益大；**check 路径** parse 只占 23–39% ⇒ 单独 PyO3
  对 check 上限 ~1.2–1.3x。
- 先吃纯 Python 算法收益（上表 1–3；消除重复扫描/渲染比换语言更便宜，且不引入 ABI 矩阵）；
  PyO3 **触发条件** = 优化后 format 仍需 ≥2x 且 parse 仍是首要项（或 check 的 parse 占比升到
  首位）；届时再评估 abi3 wheel × Python 3.11–3.13 × 三 OS 的构建与维护成本。
- 与增量关系：编辑路径已有解析层增量（tv80 语句级 67x），PyO3 的增量收益主要落在**冷启动
  全量** format/check，不替代 P3.4。

## 不做 / 否掉

- 不做"为 PyO3 而 PyO3"：无实测瓶颈点就重写 = 把风险换成维护成本。
- 不做"语义增量先于测量"：先做上表 1–3，再按新结构决定失效模型优先级。

## Gap 纳入调查（2026-11-12，作者要求）

本期目标 = **性能**（check/format）+ **工具化收口**；纳入判据 = 与目标接近 **或** 改动部件相同。
逐 gap 调查后的处置：

| gap | 关系（目标/部件） | 处置 |
|---|---|---|
| `gap-incremental-parse` | 同目标（增量 check）/同部件（`parser/incremental.py`） | **块 4 内**：残余项登记（叶子 span 补齐 / 多编辑累积 / 符号门控）；切片 0 只测「解析增量 + 全量语义」 |
| `gap-unit-graph` | 同部件（图化，块 4 前置） | "图之上做增量失效"的触发 = 块 7 开工 ⇒ 归 **0.1.6 语义失效模型**（块 4 只做切片 0，不承诺图级失效） |
| `gap-language-penetration` | 同部件（`_graph.py`） | 残余①（插件侧 AST-first 改写）**顺带进块 2**（ADR-0021 #7 触发 = 该子系统再动）；残余②（引擎取值形态假设）不纳入（框架级） |
| `gap-comment-string-span-consistency` | 近目标（注释正确性）/异部件（preprocessor + lexer） | B 侧「跨度单一来源（向词法捕获器要跨度）」进**块 5**；A 侧 yaml 块标量语义化不纳入（触发 = 往返保真需要） |
| `gap-language-pack-scope`（注释已知偏差） | 同目标（C 注释归属） | **块 5**（`TODO.md` §1.2 两项） |
| `gap-formatter-line-behavior` | 同部件（renderer） | 只纳入相邻的 **layout schema**（块 6）；空档 7/8（注释邻接 / framework 级判据）**不纳入** |
| `gap-tpc-check-external-checker` | 近目标（工具化） | **块 7**（gap 档协议已备；P2.6） |
| `gap-verification-engineering` | 同目标（验证/吞吐基础设施） | 项 1（fuzz 接受域统计对拍）与项 7（覆盖薄区 transform/renderer）进**块 8**；项 2–4 接受不改 |
| 解析回溯余量（原 `gap-parser-backtracking` / `gap-c-real-corpus` 已按收口删除） | 近目标（性能） | 块 1 把 **C 真实语料解析耗时**纳入基线；优化（atom FIRST 预过滤，须带宏/占位兜底）**不纳入本期**（0.1.6 候选；证据 CHANGELOG 块 2 / #52） |
| `gap-semantic-elaboration-boundaries` | 同部件（elaboration） | 仅作块 2/3 的**边界约束**（Elaboration 深度/宽度/CDC 为接受范围，不纳入） |
| 其余（`gap-c-*` 已收口、`gap-feature-scatter`、`gap-engine-abstraction-audit`、`gap-fragment-mode`、本档本体） | — | 不纳入（已收口 / 非本期目标） |

## 0.1.5 刻度（9 块，2026-11-12 立）

| # | 块 | 判据（"改前红"） | 止损 |
|---|---|---|---|
| 1 | 性能基线 + 常驻测试面（含 C 语料解析耗时） | `tests/perf/` 场景基线与 ratchet（新增/劣化 >10% 红；基线缺失 exit 2）+ CI/nightly 入口 | 场景 CV >10% ⇒ 预热/三次取中位再立基线 |
| 2 | 语义层优化①：端口源单遍索引（+ L1 残余①顺带） | 诊断逐字节相等 + tv80 check 降 ≥20%；L1 判据②（声明面缺失探针）在该文件不新增渗透 | <10% 放弃并落"已试"；L1 项与原结构冲突则从块 2 拆出 |
| 3 | 语义层优化②：渲染 memo + 树遍历 | 渲染调用数降 ≥50%、诊断相等；树遍历改动全量回归绿 | 单项 <10% 放弃；树遍历若引入子节点缓存语义风险 ⇒ 停止 |
| 4 | 增量 check 切片 0（warm + 解析层增量 + 全量语义） | 单文件编辑重查 tv80 ≥1.3x / picorv32 ≥1.5x，且结果 = 全量 | 低于阈值 ⇒ 只落测量/决策档；语义失效模型转 0.1.6 |
| 5 | 注释正确性：C 注释归属 2 项 + 预处理注释/字符串跨度单一来源（B 侧） | C 两项既有判据 + B 侧两条近似断言改为正确行为且真实语料诊断基线不涨 | B 侧若需改 `clean_to_raw` 契约（超范围）⇒ 只落 C 两项，B 侧另立 |
| 6 | 工具化：renderer layout schema 校验 | 非法布局（拼错原语键/类型）fail-fast（明确错误 + 非零退出）；合法布局渲染字节不变 | schema 若侵入布局表达式解析主路径 ⇒ 退回评估 |
| 7 | 工具化：外部 checker 协议（P2.6） | 语言包可声明外部 checker（命令/输出解析）+ 诊断归一化；无声明时行为不变；veryl 本体先验证 | 协议需引擎能力位变更 ⇒ 先落声明面（块标 partial） |
| 8 | 验证工程：fuzz 接受域统计对拍 + 覆盖薄区 | 随机合法程序批量对拍 Verible（接受/差异分类可解释、不新增未解释差异）；transform/renderer 薄区补测到约定阈值 | Verible 不可用 ⇒ 用仓内语料统计替代并标 partial；对拍无解释差异 ⇒ 停止扩大 |
| 9 | 0.1.5 收口（证据 + 排练 + 发布前文档） | `ci_rehearsal` 16 步 + wheel PASS；e2e FAIL 0；lint recall/FP 门禁；版本切段与文档同步 | 任一门禁红 ⇒ 不进入发布态 |
