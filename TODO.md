# TODO（短期活跃待办）

> 只列**未完成**项，完成即删（历史在 git log + 测试断言，正文不复述）。
> 每项 ≤6 行 = 现状一句 + 判据/触发条件一句 + 链到 gap/机制文档。
> **归位**：能做的进「一/二/三/四」；**触发式、暂不可达的进「五、搁置」**（不占在途队列，触发时取回）；
> 同一问题只记一处（多处出现即合并）；完整论证在 `ROADMAP.md` / `docs/gaps/gap-*.md`。
> 容量上限由 `tests/policy/test_planning_doc_budget.py` 守（超限先删旧再进新）。

## 一、在途批次：阶段 4 A2（当前主线唯一在做的块）

- [ ] **A2 预处理器收尾批次**（五项同批，逐项独立判据；验收 = 退出判据 1 实质达成）：
      **① `expand_macros` 默认统一为"开"**（A1 用户可达的前提）——默认 false 下 CLI 对合法 `#define`
      都报语法错；判据 = 默认开 + verilog 对拍 0 差异 + CLI 不再报语法错。**② `#include` 真实实现**：
      `path_forms` 接线 + 内容进流 + 缺文件/循环**给诊断**（现只 `print`）。**③ 两路径统一**：lint 与
      管线段同一输入都给诊断、都不抛异常（`_stage_lex` 现抛 `ValueError`）；顺带落地 **token 级重扫**
      （= A1 两条已声明边界：替换后再现的调用 / 实参跨行），以 **A/B 0/144 + 后缀链**为独立检查点。
      **④ `#define` 非法输入诊断面**：空名 / 畸形形参表 / 实参个数不校验 / `#`·`##` 约束违反（GCC 均
      error、本包静默）⇒ 按「语法宽进 + 诊断走 linter」给**位置正确**的诊断。**⑤ gap ⑮ 的 5 处文档漂移**。
      链：`docs/gaps/gap-c-preprocessor-scope.md` ⑨⑪⑬⑭⑮⑯⑰；`preprocessor/README.md`「已知边界」

## 二、C 包缺陷（A2 之外，能做的）

### 2.1 检查与诊断面（"该报的没报 / 报得粗"）
- [ ] **块内诊断粒度粗（每块只报一条，且报文指错位置）**：`void f(void) { a + ; b + ; }` → 1 条指向
      `b` 的 `expected '}'`，**真错在 `a + ;`**（c4 同形样本 → 2 条精确）。成因 = `CompoundStmt` 块体无
      独立语句节点 + `matcher._match_repeat` 遇错即 `break`；两条候选修法**各有实测代价**（(A) 包侧改块
      规则 ⇒ 推翻本包锁进测试的 `Declaration`/`ExprStmt` 消歧；(B) 引擎侧语句边界恢复 ⇒ 改变**所有语言**
      的坏输入诊断面）。判据：块内每条坏语句各报一条**位置正确**的诊断。
      链：`docs/gaps/gap-parser-linter-approximation.md`

### 2.2 渲染保真 / 注释归属（`gap-language-pack-scope.md`「已知偏差」）
- [ ] **#8 枚举体尾逗号后的行注释吞掉收尾 `};`**：`enum e { A, B, // note` + 换行 + `};` → 首遍
      `enum e {A, B,} // note;`，**丢 token、产物非法 C**。与 #6 同族（容器 `trailing` 槽）但 #6 只位置
      漂移，**丢 token 不能默认按 #6「归 raw 路径」结案**。判据：两遍渲染后 `};` 仍在、产物合法。
- [ ] **#3 注释归属的 token 跨度判据**：注释落在**括号内首元素前**时被上提到括号外（`int f(\n// c\nint a)`
      → 注释落在 `f` 与 `(int a)` 之间）。成因 = `_lift_gap_comments` 项间窗口上界用"迭代**末行**"，
      跨度**内部**的注释被当"该元素之前"；**收紧窗口已验证不可行**（上界改迭代首行 → 6 处门禁红：
      端口表/具名端口/声明符表/case 项/真实语料无丢注释）。判据：判据改为**迭代 token 跨度**（跨度内 →
      归跨度内部消费方）后该形态归位，且上述 6 处门禁全绿。

## 三、工具与门禁基础设施（非主线，收口时按影响做）

- [ ] **A/B 对拍工具缺"产物摘要"档**：现只对拍 `rc`/`stdout` ⇒ 声明"零可见变化"时仍要手写脚本（M1
      那次由审计方另做逐文件 SHA256）。判据：工具增产物摘要档（逐文件 `lint --json` / 渲染文本 PRE↔POST）
      + `tools/README.md` 同步一行；零可见变化收口证据改用该档。
- [ ] **`check_doc_refs` D3 不查 blockquote 续行**：`Impl:`/`Test:` 多行续行在 D3 视野外 ⇒ 引用**不存在的
      测试文件也不会红**（已删档 ADR-0017 引 `test_macro_call_node.py` 而 D3 = 0）。判据：D3 支持续行（或
      明确写 D3 边界）+ 该悬空引用能被抓到。链：`policy/check_doc_refs.py`、`policy/doc-alignment.md`
- [ ] **yaml 渲染对真实 workflow 不幂等（无门禁覆盖）**：仓库自己的 `.github/workflows/*.yml` 两遍渲染，
      第二遍把 `shell: pwsh` 后的注释**上提一行**（offset≈2349）⇒ `format(format(x)) != format(x)`；与渲染器
      接线无关。判据：该文件两遍逐字相同 + `tests/languages/yaml` 全绿。
      链：`docs/gaps/gap-formatter-line-behavior.md` 条目 6
- [ ] **CI 排练与远端 runner 的编码口径差**：开发机 `PYTHONUTF8=1`（UTF-8）、GitHub windows runner 无此
      变量（cp1252）⇒ **排练绿、CI 红**（已实测踩过）。待做：(a) `tools/ci_rehearsal.py` 的 Python 步骤注入
      `PYTHONIOENCODING=cp1252`（已验证优先于 `PYTHONUTF8`）；(b) 清扫剩余未自护脚本（现测 24 个）。
      判据：cp1252 下排练全 PASS。
- [ ] **Verilog 头部参数列表"续项不带关键字"**：`#(parameter W = 8, D = 4)` / `#(W = 8, D = 4)` 被 linter
      阻断（现只接受每项重复 `parameter`）。判据：先扫 `tests/e2e/samples/real/` 统计出现次数——有量则补
      语法，无则记既定取舍。链：`grammar/verilog/01_module/`
- [ ] **`tpc check` 跨盘输入崩栈**：`main.py:361 os.path.relpath` 对 C:↔E: 跨盘路径抛 `ValueError`（同盘
      正常）⇒ 报错非受控。判据：跨盘文件给受控诊断或正常处理。来源：A1 审计返工实测（既有缺陷）
- [ ] **跟踪文档指向 `_drafts/` 具体草稿（死链）**：`preprocessor/README.md` 1 处、`grammar/c/README.md`
      4 处 ⇒ 对 clone 者是死链，且违反 `policy/structural_budget.md`「不许写"见某草稿某节"」。
      判据：**指向具体草稿文件**的引用清零（"描述草稿区本身"的提及保留）。

## 四、预算与登记（代码结构债 / 功能散点）

- [ ] **结构欠账 S 有 50 项新增未下结论**：`python tools/structural_score.py --compare` 实测 **基线 0 →
      当前 1137**（新增 50 项，exit 1）——新代码（`linter/lookahead.py` 类体、`preprocessor/macro_expand.py`、
      `tools/feature_sites.py` 等）未按 R6 逐项判保持。判据：每项"重构删掉"或记入
      `tools/structural_kept.json`（**reason + source**），`--compare` 回 0。链：`policy/structural_budget.md`
- [ ] **功能散点步 2b**：剩余 16 个未收敛登记点（有意保留的边界，非欠账——收敛一个删一个；清单与判据见
      `docs/gaps/gap-feature-scatter.md`「步 2 收敛目标与接受边界」），**另有 3 处新增散点未登记**：
      `python tools/feature_sites.py compare` 实测 `check` 8→12、`config` 29→30、`config:lexer.pre_scan` 2→3
      ⇒ 合并登记点或写保持理由。

## 五、搁置（触发条件未到，先不动；触发时逐个取回——不占在途队列）

> 每条只留「为什么现在做不了 + 触发条件 + 链」。完整论证在对应 gap 档，不在此复述。

- **档位 `[plugins] enabled` 语义边界**：`enabled` 只门控声明面，插件规则与 Python 组件无条件加载 ⇒
  "档位 = 接受域"对不依赖新关键字的增量（`[[属性]]`）不成立。作者定调（2026-09-28）**慢慢补充、不急着选**；
  补齐前不新增依赖该语义的声明。链：`docs/gaps/gap-language-pack-scope.md`「运行时档位」节。
- **`[macro_policy] when` 声明表上提**：现役走能力插件；评估结论 = 今天不上提（只有 verilog 一个声明方）。
  触发 = 第二个语言包出现**同形**判定 ⇒ 以"`call_site` 事实**合取** → mode"小表上提，**替代而非并存**。
- **S2 链接性片：不采**（task-45）：无真阳样本 / 朴素实现 4/19 误报（含 `static int x; extern int x;`
  依 §6.2.2p423 继承 internal 的合法形态）/ 基座错位未修 / **UB 非约束**、GCC 本就诊断。触发 = 基座错位
  修完**且**出现可解析真实语料（含真阳）。
- **符号基座两处错位**：① `void f(int x);` 形参符号落 `<global>`；② `void f(void){}` 函数定义符号落
  `<FunctionScope>` ⇒ 同 TU internal+external 真 UB 漏报、"定义后 `extern`"继承链断。**已裁：另立项目**
  （F1/F2 改 P1 公开产物 ⇒ 命中升级判据 ①，契约面须回作者）；已落 N1/N2 派生视图
  （`_api.declaration_view()`，产物逐字节不变）＝"声明位置"唯一入口。链：`docs/gaps/gap-c-semantic-base.md`。
- **阶段 3 剩余片**：**S3 函数原型/定义一致性**（需**类型模型**，代价最大）｜**S5**（case/default 部分
  条款未取得原文；**枚举值重复是 C 档反证 ⇒ 永不实现**）。触发 = 按价值/代价逐片立项。来源：循环 #11 侦察。
- **CSC001 函数位 + CSC B 档 7 条**：一 id 一 kind ⇒ 函数位组合未覆盖（需"一 id 多 kind"或组件 postpass =
  引擎检查分发面）；CSC004/007–012 仅权威转述、`default=false`，转默认开需**取得原文句**或更大真实语料
  零误报（本轮仅 8 个 C 语料）；同批可议 CSC001（A 档）是否从 warning 升 `error`。来源：循环 #10 保守裁定。
- **逐声明符位宽**（`int a : 3, b : 4;` 解析失败）：标准上位宽属声明符，本包宽度绑在整个成员声明后（一个
  `DeclaratorList` 共用）；要支持需形态改动。单声明符位域与匿名占位可用。触发 = 真实语料出现该形态。
  链：`grammar/c/02_types.toml::StructMember` 注释。
- **参数位 `register`**：`void f(register int x);` 是**合法 C**（§6.7.1p4 允许参数表用 register），本包
  lint 报 2 条 blocking（参数说明符位不接受存储类）⇒ 语法面缺口。触发 = 真实语料/头文件出现。来源：循环 #10。
- **ENUM003 的 C23 豁免**：`enum E : int;` 按 N2963 **总是完整**，但本包语法面尚不支持该形态 ⇒ 现无影响；
  **将来实现该语法时** ENUM003 必须加"带底层类型 ⇒ 恒完整"豁免，否则误报。链：`grammar/c/README.md` 表头注。
- **复合字面量 `(t){1}` 的 raw 候选**：理解路径已落地（循环 #9），但**承载期建候选失败** ⇒ 不提升、不报错
  （记 `not_understood: candidate_missing`，用户面不变）。触发 = 真实语料 / check 规则出现该结构需求。
- **插件侧 AST-first 改写**（精化搬迁析出项）：插件侧仍有文本技法——`_graph.py::_is_signal_expr` 正则判
  "简单信号名"、`render_subtree` 渲染后字符串比较。动机 = 插件代码质量，须**自带验证**（无引擎侧渗透判据
  兜底）。归 L1 长期面，无触发条件。
- **引擎侧未声明的取值形态假设**（归 L1 渗透复审）：`[structure.fields]` 只声明**字段名**，引擎仍假设取值在
  `Node.content`（`analyzer/structure.py`、`analyzer/elaboration/atoms.py`）——"形态从哪里取"没进声明面，
  多形态语言包会撞。
- **循环纪律的机械化（4 项，task-52 审计派生）**：① 判据色产物门禁（`PRE=<rc>/POST=<rc>` + 命令，复用
  `ab_pipeline_compare.py` 的 PRE 机制）；② `tools/cycle_triggers.py`（`git diff --name-only` → 触发规则表，
  **须过种子集自检**才可当门禁）；③ 审计反例入库重跑（`tests/policy/data/cycle_audit/` + `--check`）；
  ④ `policy/*.md` **逐文件**行数上限（**禁用通配**：实测 223/181/153/115/100 五档超 90，数字待压缩收口后
  按实测留余量定）。触发 = 认为"循环纪律须机器化"时逐项立项。
