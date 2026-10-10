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
- [ ] **C 语义基座 P2b = 符号接进 linter 判定 + 窄档"未识别 ⇒ 内部 warning ⇒ 不再 blocking"**
      （P1 符号产物与 P2a 旁路均已交付）：把 typedef 谓词喂进收敛判定/候选排序，并**只**对
      "符号歧义导致候选全败"这一窄档把 blocking 摘成内部 warning（真语法错仍 blocking）。
      判据：`x = (myint)y;`（有 typedef 时）不再 blocking、`x = (1 + )y;` 仍 blocking、
      lint accuracy 与真实语料误报基线不退化。链：`docs/gaps/gap-c-semantic-base.md`、
      `ROADMAP.md`「C 语义层切片 1b」
- [ ] **`pre_scan` 引擎兜底正则杂质**（2026-10-10 登记，P1 遗留）：`lexer/pre_scan.py::_compile`
      对任何声明关键字**无条件**建 `\b(kw)\s+(\w+)` 兜底正则 ⇒ C 下产出 `int: typedef` 这类
      **非声明名**，包侧无法关闭（已登记在 `grammar/c/base/_pre_scan.toml` 头注，消费方按
      "pre_scan 只作提示"处理）。判据：认一个 `[pre_scan] fallback = false` 键（默认 `true`
      ⇒ 其他包零影响），C 包声明后 `pre_scan` 期记录无杂质；回归 verilog/yaml/c4 的 pre_scan 面
- [ ] **插件侧 AST-first 改写**（精化搬迁析出项）：搬迁是**逐字**的，插件侧仍有文本模式
      技法——`grammar/verilog/plugins/elaboration/_graph.py::_is_signal_expr` 正则判"简单
      信号名"、`render_subtree` 渲染后**字符串比较**。动机已是**插件代码质量**，故须
      **自带一套验证**（不再有引擎侧渗透判据兜底）。
- [ ] **引擎侧未声明的取值形态假设**（归 L1 渗透复审）：`[structure.fields]` 只声明**字段名**，
      引擎仍假设取值在 `Node.content`（`analyzer/structure.py` 单元名、
      `analyzer/elaboration/atoms.py`）——"形态从哪里取"没进声明面，多形态语言包会撞。

## 引擎与验证基础设施

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
