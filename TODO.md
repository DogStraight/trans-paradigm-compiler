# TODO（短期活跃待办）

> 只列**未完成**项，完成即删（历史在 git log + 测试断言，正文不复述）。
> 归位纪律：每项 ≤6 行 = 现状一句 + 判据/触发条件一句 + 链到 gap/机制文档；
> 中长期 / backlog / 触发式 → `ROADMAP.md`；**现状边界** → `docs/gaps/gap-*.md`；
> **预期外 / 未定判观察** → `DRAFT.md`。容量上限由
> `tests/policy/test_planning_doc_budget.py` 守（超限先删旧再进新）。

## C 语言包（0.1.3 交付面之后的未完项）

- [ ] **块内诊断粒度粗（每块只报一条，且报文指错位置）**：`void f(void) { a + ; b + ; }`
      → 1 条指向 `b` 的 `expected '}'`，**真错在 `a + ;`**（c4 同位样本 → 2 条精确诊断）。
      成因 = `CompoundStmt` 块体无独立语句节点 + `matcher._match_repeat` 遇错即 `break`。
      两条候选修法**各有已实测代价**：(A) 包侧改块规则 ⇒ 推翻本包刻意选定并锁进测试的
      `Declaration`/`ExprStmt` 消歧；(B) 引擎侧语句边界恢复 ⇒ 改变**所有语言**的坏输入
      诊断面。现状刻意不改（不影响合法代码零误报）。
      判据：块内每条坏语句各报一条**位置正确**的诊断。链：`docs/gaps/gap-parser-linter-approximation.md`
- [ ] **预处理两项（`#include` / `#define`）**：`tools/c_acceptance.py`（42 条构造）仅剩的
      **接受面空洞**；属阶段 4，先立项（详案见 `ROADMAP.md`「C 语言包」）。
      判据：两项进 AST + 负样本被拒 + 工具空洞归零。
- [ ] **枚举体尾逗号后的行注释吞掉收尾 `};`**（`enum e { A, B, // note` + 换行 + `};`
      → 首遍 `enum e {A, B,} // note;`，**丢 token、产物非法 C**）。与渲染现状 #6 同族
      （容器 `trailing` 槽）但 #6 只位置漂移，**丢 token 不能默认按 #6「归 raw 路径」结案**
      ——待作者单独判。链：`docs/gaps/gap-language-pack-scope.md`「已知偏差」#8
- [ ] **注释归属的 token 跨度判据（解析侧，#3 形态）**：注释落在**括号内首元素前**时位置
      被提到括号外（`int f(\n// c\nint a)` → 注释落在 `f` 与 `(int a)` 之间）。成因 =
      `_lift_gap_comments` 的项间窗口上界用"迭代**末行**"，迭代跨度**内部**的注释也被当
      "该项之前"上浮；**收紧窗口已验证不可行**（上界改迭代**首行** → 6 处门禁变红：端口表/
      具名端口/声明符表/case 项/真实语料无丢注释）。要修需把归属判据从行号窗口改为
      **迭代 token 跨度**（跨度内 → 归跨度内部消费方）。判据：该形态注释归括号内，且上述
      6 处门禁全绿。链：`docs/gaps/gap-language-pack-scope.md`「已知偏差」#3
- [ ] **档位（`[plugins] enabled`）语义边界**：`enabled` 只门控**声明面**（含词法扩展）；
      插件规则文件与 Python 组件无条件加载 ⇒ **不依赖新关键字的增量**（`[[属性]]`）在基线档
      也解析，"档位 = 接受域"对它不成立。作者定调（2026-09-28）：**慢慢补充，不急着选**；
      补齐前不新增依赖该语义的声明。事实面、两种候选语义与代价、真实症状见
      `docs/gaps/gap-language-pack-scope.md`「运行时档位：`enabled` 的语义边界」节
- [ ] **逐声明符位宽**（`int a : 3, b : 4;` 解析失败）：标准里位宽属声明符，本包宽度绑在
      整个成员声明后（一个 `DeclaratorList` 共用一个宽度）；要支持需形态改动。
      当前单声明符位域与匿名占位可用。链：`grammar/c/02_types.toml::StructMember` 注释
- [ ] **复合字面量 `(t){1}` 的 raw 候选（承载期未覆盖）**：理解路径已落地（循环 #9），但该形态
      **承载期建候选失败** ⇒ 不提升、不报错（记 `not_understood: candidate_missing`，用户面不变）。
      触发条件 = 真实语料 / check 规则出现对该结构的需求（届时补承载期的候选建法，属 parser 写面）。
      链：`docs/gaps/gap-c-semantic-base.md`（P4）；来源：循环 #9 交付边界
- [ ] **参数位 `register` 的语法缺口**：`void f(register int x);` 是**合法 C**（§6.7.1p4 允许
      register 用于参数表），但 C 包 lint 报 **2 条 blocking**（参数说明符位不接受存储类）⇒ 属**语法面**
      缺口（与本批语义检查不同层）。触发条件 = 真实语料/头文件出现该形态。来源：循环 #10 实测
- [ ] **CSC001 函数位覆盖**（一 id 一 kind 的机制限制）：一条 check 规则 id 只能绑一个 `sym.kind` ⇒
      CSC001 只覆盖对象位（`kind=variable`），`static extern int f(void);` 的**函数位组合未覆盖**。
      闭合需"一 id 多 kind"或组件自带 postpass（属引擎检查分发面变更）。触发条件 = 出现该形态真实需求，
      或"一 id 多 kind"被别的规则一并需要。来源：循环 #10 交付边界
- [ ] **CSC B 档 7 条转默认开**（CSC004/007/008/009/010/011/012）：当前 `default=false`（opt-in）——
      仅有权威转述、未取得标准原文句。触发条件 = 取得原文句（C11/C23 §6.7.1 各段）**或**更大真实语料
      实测零误报（本轮仅 8 个 C 语料）。同批可议：CSC001（A 档）是否从 warning 升 `error`。
      来源：循环 #10 保守裁定
- [ ] **阶段 3 剩余片**（S2/S3/S4/S5；循环 #11 侦察实测，**均"当前静默"**）：
      **S2 链接性**（同 TU 同时具 internal+external linkage = UB，§6.2.2 原文；机制最省，但
      **FP 风险中高**——头文件 `extern`/`static` 模式，须实现作用域链继承判定）｜**S4 标签**
      （§6.8.1「Label names shall be unique within a function.」+ §6.8.6.1 goto 目标，**A 档原文、
      FP≈0**，但需 **postpass 形态**、label 当前不进符号表）｜**S3 函数原型/定义一致性**（需
      **类型模型**，代价最大）｜S5（case/default 部分条款未取得原文；**枚举值重复是 C 档反证 ⇒
      永不实现**）。触发条件 = 按价值/代价逐片立项。链：`_drafts/p3_next_plan.md`；来源：循环 #11 侦察
- [ ] **ENUM003 的 C23 豁免缺口**：`enum E : int;`（固定底层类型枚举）按 N2963 **总是完整**，但本包
      语法面尚不支持该形态（实测 lint 拒）⇒ 现无影响；**将来实现该语法时** ENUM003 必须加
      "带底层类型 ⇒ 恒完整"豁免，否则误报。来源：循环 #11 交付边界（已记 `grammar/c/README.md` 与规则表头注）
- [ ] **插件侧 AST-first 改写**（精化搬迁析出项）：搬迁是**逐字**的，插件侧仍有文本模式
      技法——`grammar/verilog/plugins/elaboration/_graph.py::_is_signal_expr` 正则判"简单
      信号名"、`render_subtree` 渲染后**字符串比较**。动机已是**插件代码质量**，故须
      **自带一套验证**（不再有引擎侧渗透判据兜底）。
- [ ] **引擎侧未声明的取值形态假设**（归 L1 渗透复审）：`[structure.fields]` 只声明**字段名**，
      引擎仍假设取值在 `Node.content`（`analyzer/structure.py` 单元名、
      `analyzer/elaboration/atoms.py`）——"形态从哪里取"没进声明面，多形态语言包会撞。

## 引擎与验证基础设施

- [ ] **A/B 对拍工具缺"产物摘要"档**：`tools/ab_pipeline_compare.py` 现只对拍 `rc` / `stdout`
      ⇒ 声明"零可见变化"时仍要临时手写脚本（M1 那次由审计方另做逐文件 SHA256）。
      判据：工具增产物摘要档（逐文件 `lint --json` / 渲染文本摘要 PRE↔POST 对照），
      `tools/README.md` 同步一行；零可见变化的收口证据改用该档。
      来源：循环 #5 假红复盘（派生，见 `policy/collaboration.md`「循环执行细则」）

- [ ] **`check_doc_refs` 的 D3 不查 blockquote 延续行**：`Impl:` / `Test:` 的多行续行
      （ADR/机制文档里 `> Test: a.py ·` 换行 `b.py`）在 D3 视野外 ⇒ 引用**不存在的测试
      文件也不会红**（实测：已删档的 ADR-0017 引 `test_macro_call_node.py` 而 D3 = 0）。
      判据：D3 支持续行（或在机制文档明确 D3 边界），且该悬空引用能被抓到。
      链：`policy/check_doc_refs.py`、`policy/doc-alignment.md`
- [ ] **yaml 渲染对真实 workflow 文件不幂等（当前无门禁覆盖）**：对仓库自己的
      `.github/workflows/*.yml` 跑两遍渲染，第二遍把 `shell: pwsh` 后的注释**上提一行**
      （offset≈2349）⇒ `format(format(x)) != format(x)`；与渲染器接线无关（裸/生产接线输出
      逐字相同）。判据：该文件两遍渲染逐字相同，且 `tests/languages/yaml` 全绿。
      链：`docs/gaps/gap-formatter-line-behavior.md` 条目 6
- [ ] **CI 排练与远端 runner 的编码口径差**：开发机 `PYTHONUTF8=1` ⇒ 子进程 stdout 是
      UTF-8，而 GitHub windows runner 无此变量（cp1252）⇒ **排练绿、CI 红**（已实测踩过）。
      待做：(a) `tools/ci_rehearsal.py` 的 Python 步骤注入 `PYTHONIOENCODING=cp1252`
      （已验证该变量优先于 `PYTHONUTF8`，能逼出未自护脚本）；(b) 清扫剩余未自护脚本
      （口径 = 打印非 ASCII 的独立入口脚本一律自护 stdout；**现测 24 个**：`tools/` 12、
      `tests/e2e` 6、`tests/differential` 2、`tests/fuzz/shrink`、`packaging/build_pipeline.py`、
      `parser/rule_selector.py`、`main.py`）。判据：cp1252 下排练全 PASS。
- [ ] **Verilog 头部参数列表的"续项不带关键字"形态**：`#(parameter W = 8, D = 4)` /
      `#(W = 8, D = 4)` 被 linter 阻断（现只接受每项都重复 `parameter`）。
      判据：先扫真实语料（`tests/e2e/samples/real/`）统计该形态出现次数——有量则补语法，
      无则记为既定取舍。链：`grammar/verilog/01_module/`
- [ ] **结构欠账 S 有 16 项新增未下结论**：`python tools/structural_score.py --compare`
      实测 **基线 0 → 当前 287**（新增 16 项，exit 1）——新代码（`tools/feature_sites.py`、
      `analyzer/elaboration/contract.py`、`core/engine_capabilities.py`、
      `config_registry.merge_by_name` 等）未按 R6 逐项判保持。判据：每项"重构删掉"或记入
      `tools/structural_kept.json`（**reason + source**），`--compare` 回 0。
      链：`policy/structural_budget.md`（口径与停止规则）
- [ ] **功能散点步 2b：剩余 16 个未收敛登记点**（属有意保留的边界，非欠账——收敛一个删一个）。
      清单与判据见 `docs/gaps/gap-feature-scatter.md`「步 2 收敛目标与接受边界」
- [ ] **`[macro_policy] when` 声明表上提**（触发条件式）：现役"宏处置判定"走能力插件
      （`[capabilities] macro_policy`）。评估（`_drafts/preprocessor_prototype_assessment.md`，2026-10-17）
      结论 **今天不上提**——按"多语言共有且形态稳定"判据，实测只有 verilog 一个声明方。
      触发条件 = 第二个语言包出现**同形**判定 ⇒ 以"既有 `call_site` 事实**合取** → mode"的小表上提，
      **替代而非并存**（两处同声明 ⇒ 加载期 `ConfigError`）。链：`preprocessor/README.md`「跨语言文本能力原型」
- [ ] **符号基座两处错位**（**影响任何"文件域 / 作用域"语义检查**，非仅链接性；2026-10-17 实测）：
      ① `void f(int x);` 的**形参符号落 `<global>`**（`decl_node=ParamDecl`、`is_file=True`）⇒ 文件域判定误判；
      ② `void f(void){}` 的**函数定义符号落 `<FunctionScope>`**（`scope_kind=function`）⇒
      `void f(void); static void f(void){}` 这类真 UB **漏报**、"定义后的 `extern`"继承链断。
      修法与影响面（**含是否触 P1 公开产物契约面**）评估中（task-46）。**已确认应优先修**——它是语义检查的地基。
      链：`docs/gaps/gap-c-semantic-base.md`
- [ ] **S2 链接性片：不采（判据不足；触发条件式）**：task-45 实测 ⇒ ① **无真阳样本**（可解析真实 C 语料
      仅 8 个小文件、冲突命中 0；大语料 503 个 `.c/.h` 抽样 **40/40 抛 `ValueError`**）② 朴素实现 **4/19 误报**，
      含**高频合法形态**（`static int x; extern int x;` 依 §6.2.2p423 **继承 internal ⇒ 合法**）③ **基座两处
      错位**未修 ④ 条款是 **UB 而非约束**、GCC/clang 本就诊断 ⇒ 价值低于 tags/labels 两片。
      **触发条件** = 基座两处错位修完 **且** 出现可解析的真实 C 语料（含真阳样本）。
      若届时做：最小形态 = 文件域 + 排除形参位/FuncDef 位 + **必须实现 p423 继承** + `default=false`（覆盖率约一半）。
- [ ] **预处理指令的两条路径行为不一致**：`#include` 在 CLI lint 给 `lexer-error`（blocking），
      而在**管线段抛 `ValueError`** ⇒ 同一输入两种表现。**并入阶段 4 首片**（正是阶段 4 的指令面）。
      链：`docs/gaps/gap-c-preprocessor-scope.md`
