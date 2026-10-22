# TODO（短期活跃待办）

> 只列**未完成**项，完成即删（历史在 git log + 测试断言，正文不复述）。
> 每项 ≤6 行 = 现状一句 + 判据/触发条件一句 + 链到 gap/机制文档。
> **归位**：能做的进「一/二/三/四」；**触发式、长期规划项进策略层（`docs/decisions/` 的策略型 ADR）**，
> 不占本档；同一问题只记一处（多处出现即合并）；完整论证在 `ROADMAP.md` / `docs/gaps/gap-*.md`。
> 容量上限由 `tests/policy/test_planning_doc_budget.py` 守（超限先删旧再进新）。

## 一、C 包缺陷（能做的）

### 1.1 检查与诊断面（"该报的没报 / 报得粗"）
- [ ] **块内诊断粒度粗（每块只报一条，且报文指错位置）**：`void f(void) { a + ; b + ; }` → 1 条指向
      `b` 的 `expected '}'`，**真错在 `a + ;`**（c4 同形样本 → 2 条精确）。成因 = `CompoundStmt` 块体无
      独立语句节点 + `matcher._match_repeat` 遇错即 `break`；两条候选修法**各有实测代价**（(A) 包侧改块
      规则 ⇒ 推翻本包锁进测试的 `Declaration`/`ExprStmt` 消歧；(B) 引擎侧语句边界恢复 ⇒ 改变**所有语言**
      的坏输入诊断面）。判据：块内每条坏语句各报一条**位置正确**的诊断。
      链：`docs/gaps/gap-parser-linter-approximation.md`

### 1.2 渲染保真 / 注释归属（`gap-language-pack-scope.md`「已知偏差」）
- [ ] **展平行内行尾注释的 LineSuffix 落地**：行终止注释落在**展平行内**的声明符/说明符之间
      时，LineSuffix 在原子节点边界就地落地，把后续 token 吞进注释（`struct S { int // c\nx; };`
      渲染成 `int // c x;`，**旧语法同样坏**；#44 对抗审计发现）。修法 = 渲染器让行终止
      LineSuffix 跨节点边界延迟到**全局**下一个换行点（`doc._resolve_line_suffix` 的作用域
      从节点 doc 提到整棵树）。触发 = 真实语料出现该形态；判据 = 复现渲染 token 序列与源
      相同且幂等（`test_c_declaration_spec_order.py` 现已锁"注释不丢"一侧）。
- [ ] **注释簿记事务化 + 原子节点领取面**（#44 审计 B）：声明符优先交替回滚后，typedef 名后的
      注释（`extern T // c\nv;` 行尾、`extern\n// c\nT *p;` 独占行）可能被去重吞掉；试修
      （行尾台账/锚点集进快照）在 C 可行但触发 verilog 注释恢复回归（端口注释位置漂移），已
      回退。修法 = 事务化注释簿记 + `_claim_head_comments` 引入"节点可承载子节点"判据。
      触发 = 真实语料出现该形态；判据 = 两类最小复现注释不丢 + 幂等，且 verilog
      `test_comment_restore` 全绿。
- [ ] **#3 注释归属的 token 跨度判据**：注释落在**括号内首元素前**时被上提到括号外（`int f(\n// c\nint a)`
      → 注释落在 `f` 与 `(int a)` 之间）。成因 = `_lift_gap_comments` 项间窗口上界用"迭代**末行**"，
      跨度**内部**的注释被当"该元素之前"；**收紧窗口已验证不可行**（上界改迭代首行 → 6 处门禁红：
      端口表/具名端口/声明符表/case 项/真实语料无丢注释）。判据：判据改为**迭代 token 跨度**（跨度内 →
      归跨度内部消费方）后该形态归位，且上述 6 处门禁全绿。

## 二、工具与门禁基础设施（非主线，收口时按影响做）

- [ ] **A/B 对拍工具 `--mode inproc` 不可用**：`--plugins` 默认 `grammar/c/plugins`
      ⇒ verilog `GrammarError`（C 插件注入 verilog 规则）；改指后 JSON 采样报
      `JSONDecodeError`。修好才能用 inproc 档当证据。**另**：`--products` 产物摘要档
      已交付（循环 #29；CLI 档逐文件比 lint JSON + `tpc format` 渲染）。
      链：`tools/ab_pipeline_compare.py`
- [ ] **yaml 渲染对真实 workflow 不幂等（无门禁覆盖）**：仓库自己的 `.github/workflows/*.yml` 两遍渲染，
      第二遍把 `shell: pwsh` 后的注释**上提一行**（offset≈2349）⇒ `format(format(x)) != format(x)`；与渲染器
      接线无关。判据：该文件两遍逐字相同 + `tests/languages/yaml` 全绿。
      链：`docs/gaps/gap-formatter-line-behavior.md` 条目 6
- [ ] **CI 排练与远端 runner 的编码口径差**：开发机 `PYTHONUTF8=1`（UTF-8）、GitHub windows runner 无此
      变量（cp1252）⇒ **排练绿、CI 红**（已实测踩过）。待做：(a) `tools/ci_rehearsal.py` 的 Python 步骤注入
      `PYTHONIOENCODING=cp1252`（已验证优先于 `PYTHONUTF8`）；(b) 清扫剩余未自护脚本（现测 24 个）。
      判据：cp1252 下排练全 PASS。
- [ ] **跨语言同进程后 C 包 postpass 静默丢失**：C→verilog→C（同进程两个 `ProjectChecker`）时
      `setup_grammar` 清空 `_loaded_components`、`SharedComponents` 缓存命中不重装 ⇒ 第二次 C 的
      CSC/LAB/MAC 诊断全丢（循环 #21 审计实测；单语言 CLI 不复现，库入口受影响）。判据：C→V→C
      两轮 check 诊断集合一致。链：`analyzer/shared_components.py`、`parser/__init__.py::setup_grammar`
- [ ] **`eval_benchmark` 丢弃 parse 失败文件的 semantic**：`not f.get("parse_ok")` 直接 `continue`
      （两处）⇒ C 样本接入后事实型 check（如 too-few 的 MAC001）会被当"不可对拍"低报。判据：C 样本
      接入时 semantic 事实型码仍被收集（或显式登记"benchmark 只对语法完整文件"口径）。
      链：`tests/e2e/eval_benchmark.py`、`docs/gaps/gap-c-preprocessor-scope.md` ㉒

- [ ] **C 真实语料解析回溯成本（性能）**：cJSON.c 单文件解析 ~50–90s（#49 前已有；
      真实语料门禁单次 ≈90–110s）。成因疑似 atom/后缀候选重复回溯（表达式含大量嵌套
      括号/成员链时呈指数）；优化面 = atom FIRST 预过滤（已加，效果有限）/位置级 memo。
      判据：全量语料门禁 ≤30s 且解析结果不变。链：`tests/e2e/eval_diag_baseline_c.py`
## 三、预算与登记（代码结构债 / 功能散点）

- [ ] **T2 `pre_scan` 专项清理**（三任务路线图；ADR-0024 已复裁）：T2a ✅ 复合字面量 typedef
      直接建树（pre_scan 零承重）；T2b = 删 pre_scan 本体/配置/两期产物 + 符号提示接线；
      T2c = 删 raw 管线（含 67 条 skip 资格测试）——先证后删（raw 生产路径无消费者）。
      判据 = ADR 各切片判据 + 受影响套件/全量/A/B/语料门禁。链：`ROADMAP.md` P2.9
- [ ] **T3 双包抽象对照按部件审查**（三任务路线图，多轮）：C/Verilog 逐部件查抽象泄露，部件序
      lexer/preprocessor → parser → linter → analyzer → transform/renderer → pipeline/config；每部件
      用判据②声明面缺失探针 + ③弱信号 + 第二语言复用实验，输出 leak 清单（修复立项/登记接受）
      并回填矩阵。判据/路线见 `docs/gaps/gap-engine-abstraction-audit.md`。


- [ ] **结构欠账 S 有 71 项新增未下结论**：`python tools/structural_score.py --compare` 实测 **基线 0 →
      当前 1341（Δ +1341，新增 71 项，exit 1）**——新代码（`linter/lookahead.py` 类体、`preprocessor/macro_expand.py`、
      `tools/feature_sites.py`、循环 #21 的 `preprocessor/macro_timeline.py` / `map_invocations_to_source` 等）未按 R6
      逐项判保持。判据：每项"重构删掉"或记入 `tools/structural_kept.json`（**reason + source**），`--compare` 回 0。
      链：`policy/structural_budget.md`
- [ ] **功能散点步 2b**：剩余 16 个未收敛登记点（有意保留的边界，非欠账——收敛一个删一个；清单与判据见
      `docs/gaps/gap-feature-scatter.md`「步 2 收敛目标与接受边界」），**另有新增散点未登记**：
      `python tools/feature_sites.py compare` 实测 **`check` 8→13**（其中 `check:MAC001` 为循环 #21 新增实例）、
      **`config` 29→30**、**`config:lexer.pre_scan` 2→3** ⇒ 合并登记点或写保持理由。

## 四、策略层（不进本档）

> 触发式 / 长期规划项**不占待办队列**：结论（不做/暂缓/另立）、为什么现在不做、触发条件统一在
> `docs/decisions/` 的**策略型 ADR**（2026-10-17 定：长期项不列待办）。触发出现时按体量取回本档或
> `ROADMAP.md`；实现后删该 ADR 对应行（表空即删该 ADR）。

