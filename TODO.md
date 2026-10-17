# TODO（短期活跃待办）

> 只列**未完成**项，完成即删（历史在 git log + 测试断言，正文不复述）。
> 归位纪律：每项 ≤6 行 = 现状一句 + 判据/触发条件一句 + 链到 gap/机制文档；
> 中长期 / backlog / 触发式 → `ROADMAP.md`；**现状边界** → `docs/gaps/gap-*.md`；
> **预期外 / 未定判观察** → `DRAFT.md`。容量上限由
> `tests/policy/test_planning_doc_budget.py` 守（超限先删旧再进新）。

## C 语言包（0.1.3 交付面之后的未完项）

- [ ] **块内诊断粒度粗（每块只报一条，且报文指错位置）**：`void f(void) { a + ; b + ; }` → 1 条指向 `b`
      的 `expected '}'`，**真错在 `a + ;`**（c4 同位样本 → 2 条精确）。成因 = `CompoundStmt` 块体无独立
      语句节点 + `matcher._match_repeat` 遇错即 `break`。两条候选修法**各有实测代价**：(A) 包侧改块规则 ⇒
      推翻本包锁进测试的 `Declaration`/`ExprStmt` 消歧；(B) 引擎侧语句边界恢复 ⇒ 改变**所有语言**的坏输入
      诊断面。现状刻意不改（合法代码零误报）。判据：块内每条坏语句各报一条**位置正确**的诊断。
      链：`docs/gaps/gap-parser-linter-approximation.md`
- [ ] **`#include` 真实实现（A2）**：`tools/c_acceptance.py` 的两个预处理样本现按"被消费且无异常"
      接受（指令行→整行 marker 注释），**`#include` 未真实包含**（`path_forms` 未接线、缺文件只
      `print`、内容未进流）⇒ 退出判据 1 实质未达。判据：包含内容进流 + 缺文件/循环**给诊断** +
      管线段与 lint 两路径一致。链：`docs/gaps/gap-c-preprocessor-scope.md` ⑨⑬⑭
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
- [ ] **阶段 3 剩余片（S3/S5；S4 标签已交付 #12，S2 见下条"不采"）**：**S3 函数原型/定义一致性**
      （需**类型模型**，代价最大）｜**S5**（case/default 部分条款未取得原文；**枚举值重复是 C 档反证 ⇒
      永不实现**）。触发条件 = 按价值/代价逐片立项。来源：循环 #11 侦察（S4 的 §6.8.1「Label names shall
      be unique within a function.」+ §6.8.6.1 已落 `checks/labels`）
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
- [ ] **结构欠账 S 有 50 项新增未下结论**：`python tools/structural_score.py --compare` 实测 **基线 0 →
      当前 1137**（新增 50 项，exit 1）——新代码（`linter/lookahead.py` 类体、`preprocessor/macro_expand.py`、
      `tools/feature_sites.py` 等）未按 R6 逐项判保持。判据：每项"重构删掉"或记入
      `tools/structural_kept.json`（**reason + source**），`--compare` 回 0。链：`policy/structural_budget.md`
- [ ] **功能散点步 2b：剩余 16 个未收敛登记点**（有意保留的边界，非欠账——收敛一个删一个；清单与判据见
      `docs/gaps/gap-feature-scatter.md`「步 2 收敛目标与接受边界」），**另有 3 处新增散点未登记**：
      `python tools/feature_sites.py compare` 实测 `check` 8→12、`config` 29→30、`config:lexer.pre_scan` 2→3
      ⇒ 合并登记点或写保持理由。
- [ ] **`[macro_policy] when` 声明表上提**（触发式）：现役"宏处置判定"走能力插件（`[capabilities]
      macro_policy`）。评估结论 **今天不上提**——按"多语言共有且形态稳定"判据，实测只有 verilog 一个声明方。
      触发条件 = 第二个语言包出现**同形**判定 ⇒ 以"`call_site` 事实**合取** → mode"的小表上提，**替代而非
      并存**（两处同声明 ⇒ 加载期 `ConfigError`）。链：`preprocessor/README.md`「跨语言文本能力原型」
- [ ] **符号基座两处错位**（**影响任何"文件域 / 作用域"语义检查**，非仅链接性；2026-10-17 实测）：
      ① `void f(int x);` 的**形参符号落 `<global>`**（`decl_node=ParamDecl`、`is_file=True`）⇒ 文件域误判；
      ② `void f(void){}` 的**函数定义符号落 `<FunctionScope>`** ⇒ `void f(void); static void f(void){}` 真 UB
      **漏报**、"定义后的 `extern`"继承链断。评估完成（task-46）：F1/F2 会改 P1 公开产物 ⇒ **命中升级判据
      ①、另立**；已落 **N1/N2 派生视图**（`_api.declaration_view()`，产物逐字节不变）＝"声明位置"唯一入口。
      ⚠ 基座档 `docs/gaps/gap-c-semantic-base.md` **已 200/200 行（满）** ⇒ 暂登记于此，待该档裁剪时并入。
      链：`docs/gaps/gap-c-semantic-base.md`
- [ ] **S2 链接性片：不采（判据不足；触发式）**：task-45 实测 ⇒ ① **无真阳样本**（可解析真实 C 语料仅
      8 个小文件、冲突命中 0；大语料 503 个 `.c/.h` 抽样 40/40 抛 `ValueError`）② 朴素实现 **4/19 误报**，
      含高频合法形态（`static int x; extern int x;` 依 §6.2.2p423 **继承 internal ⇒ 合法**）③ 基座两处错位
      未修 ④ **UB 非约束**、GCC/clang 本就诊断。**触发** = 基座错位修完 **且**出现可解析真实语料（含真阳）。
- [ ] **预处理指令的两条路径行为不一致**：`#include` 在 CLI lint 给 `lexer-error`（blocking），
      而在**管线段抛 `ValueError`**（调用栈 `pipeline/__init__.py:538 _stage_lex` →
      `lexer/main_lexer.py:1033 refine_type`：lint 路径有兜底、`_stage_lex` 没有）⇒ 同一输入两种表现。
      **并入 A2**（与 `#include` 真实实现同批，正是阶段 4 的指令面），验收含"**同一输入两条路径都给
      诊断、都不抛异常**"；**不单独**加 `_stage_lex` 守卫（随 A2 一起做）。链：`docs/gaps/gap-c-preprocessor-scope.md` ⑬
- [ ] **A1 用户不可达：`expand_macros` 默认 false**（A2 首项）：实测 `expand_macros=True` 时 C 宏生效
      （`error=''`），默认 false 下 **CLI 对合法 `#define` 都报语法错** ⇒ A1 能力对用户不可见。判据：
      默认统一为"开" + verilog 对拍 0 差异 + CLI 上 `#define` 不再报语法错。链：gap ⑬
- [ ] **`tpc check` 跨盘输入崩栈**：`main.py:361 os.path.relpath` 对 C:↔E: 跨盘路径抛 `ValueError`
      （同盘正常）⇒ 报错非受控。判据：跨盘文件给受控诊断或正常处理。来源：A1 审计返工实测（既有缺陷）
- [ ] **跟踪文档指向 `_drafts/` 具体草稿（死链）**：`preprocessor/README.md` 1 处、`grammar/c/README.md` 4 处
      —— `_drafts/` 在 `.gitignore` ⇒ 对 clone 者是死链，且违反 `policy/structural_budget.md`「不许写"见某
      草稿某节"」。判据：**指向具体草稿文件**的引用清零（"描述草稿区本身"的提及保留）。
- [ ] **循环纪律的机械化（4 项，派生自 task-52 审计的反例）**：① 判据色产物门禁（`PRE=<rc>/POST=<rc>` +
      命令，复用 `ab_pipeline_compare.py` 的 PRE 机制）；② `tools/cycle_triggers.py`（`git diff --name-only`
      → 触发规则表，**须过种子集自检**才可当门禁）；③ 审计反例入库重跑（`tests/policy/data/cycle_audit/`
      + `--check`）；④ `policy/*.md` **逐文件**行数上限（**禁用通配**：实测 223/181/153/115/100 五档超 90；
      数字待压缩收口后按实测留余量定）。触发条件 = 认为"循环纪律须机器化"时逐项立项。来源：循环 #14 审计
- [ ] **A1 返工（审计 10 P0 + 4 P1）**：独立审计判 A1 `failed`——`#`/`##` **两侧空格即失效**、调用点实参切分
      **不认字面量**（`F("x,y",3)`→`"x+y"`）、裸调用正则**短名吃长名前缀**（`A`/`AB`）、函数宏**无 `(` 被当
      对象宏且替换后不重扫**；P1：`#__VA_ARGS__`、`undef` 不清形参、跨行块注释掩码、实参内注释折叠。
      **根因 = 两条展开路径**（token/hideset vs 预展开+正则插入）。判据：`_drafts/audit_a1_counterexamples.py`
      0 偏差 + 端到端用例。**来源：独立审计**（Lead 已复现 5 条）；执行 = `task-53`
- [ ] **`#define` 约束违反的诊断面（A2）**：审计登记的「非法输入静默」四项——空名 `#define`、畸形形参表
      （`F(a,)` / `F(,a)` / `F(...,a)` / `F(a b)` / `F(a,a)`）、**实参个数不校验**（`F(1)` 给两形参 → `1+`）、
      `#`/`##` 约束违反（`#` 非形参、首/尾 `##`、非法粘贴如 `CAT(1,+)`）。GCC 均报 error，本包静默。
      **归 A2 诊断面**（tpc 惯例：语法宽进 + 诊断走 linter，不硬 fail-fast）。判据：各形态给**位置正确**的诊断。
      来源：A1 独立审计（2026-10-17）
