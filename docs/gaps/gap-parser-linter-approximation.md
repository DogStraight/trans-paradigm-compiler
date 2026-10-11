# Gap — parser/linter 错误处理近似（无解析器恢复 + 启发式边界）

- 状态：接受（设计选择，标注源码；非待闭环）。宏落语法位的情形不走 parser 恢复：宏边界节点
  由管线就树产生、句级检查前移 linter 展开路径（跳过能力本就在 linter，不必在 parser 重建）。
- 关联：`linter/linter_architecture.md`（已知边界表）
- 参照：yacc/antlr 的错误恢复（skip-to-sync）、svlint/verible 对坏输入的容错

## 边界是什么

**parser 无错误恢复**：经典递归下降 + Pratt（LL 风格）——非 LR/GLR，且无解析器级错误恢复
（无 skip-to-sync-and-continue）。语法错误由**前置 linter** 拦截并阻断管线；若畸形输入漏过
linter，parser truncation **也阻断管线**（2026-08-22 fuzz 发现：截断解析曾渲染部分输出并报
`success=True`——静默内容丢失，已修）。

**linter 启发式不可避免**：前置 linter 工作在坏代码上，错误恢复是对开放坏输入集的有限近似。
少数兜底（语句结束 = 派生 `_stmt_ends` ∪ 行尾 newline 惯例；容器结束 = 匹配失败回退派生
`_stmt_ends`）是显式标注的"语言约定近似"，不能完全从语法推导——已在源码标注。

**候选歧义面（2026-10-10 实测，C 语义基座调研带出）**：linter 的候选分类在 L2 试解析后只保留
`best=(errs, consumed, name)`，**全匹配候选集被丢弃** ⇒ 两类现状：
① **平手静默择一**：`int myint;\nmyint *b;` 该位点 `Declaration`/`StructMember`/`ExprStmt`
三者 `errs=0/consumed=4`，按注册序取一、**0 条诊断**；
② **候选全败 ⇒ 阻断**：`x = (myint)y;` 五候选全 `errs≥1` ⇒ 2 条 blocking 诊断 ⇒ 管线
`success=False`、**输出空串**（真正丢内容的是这一档）。
另：`ident_candidates` 是**全局单一集合**、上下文只用于 discovery 扫描 ⇒ 顶层 `StructMember`
这类伪候选也会算进"全匹配"（判定收敛必须先按上下文过滤）。
⇒ 相应能力面（判"候选是否收敛"、内部 warning、raw 暂缓建树、analyzer 理解路径）见
`docs/gaps/gap-c-semantic-base.md`；本节只记这条**近似边界**本身。

## 为什么接受（影响面）

- 语法错误由 linter 单点拦截 + truncation 双保险阻断，"无恢复"不会静默产出坏输出；
  恢复功能（skip-to-sync）收益低、实现贵，且会与 linter 职责重叠。
- linter 启发式覆盖的是"坏输入"这个开放集，有限近似不可避免——精确性靠 e2e lint 语料门禁
  锁住：**错误样本 33/33 全检出、合法样本 0 误报**。复现：
  `python tests/e2e/eval_lint_accuracy.py`（实测 `err_total 33 / detected 33 / miss 0 /
  valid_total 7 / fp 0`）。

**歧义位点 raw 暂缓建树（P3/P3b）：先做"资格判定"，raw 与 P4 原子落地**（2026-10-10，循环 #4–#5）：
- **P3 首次实现（整句 raw）已被独立审计证伪**（语句级 raw 吞同句无关真错，7 类反例）⇒ 整体回退。
- **P3b-M1 已落地（零用户可见变化）**：只做**资格判定**——① **替换式试解析**（把 `( id )` 的
  标识符按类型名形态替换后**重跑同一候选集**，整句通过才算"该句唯一问题是符号歧义"）；
  ② **只认 typedef 命名空间**（kind 语义由包声明）；③ **声明位置先后（行+列）+ 深度守卫**
  （`decl_depth ≤ use_depth`）。判据与实测见 `CHANGELOG.md`；`pre_scan_with_lines` 是并行读取面。
- **M2（raw + 窄档摘诊断）与 P4 原子落地**：raw 段的合法性由 analyzer 用 `phase="analyze"` 的
  **精确符号面校验**（该校验正是本档接受的近似面之外的一层），校验不过 ⇒ 报错、不静默。同批判据：
  **作用域遮蔽**（`typedef int t; void f(void){ int t; x=(t)y; }`——`pre_scan` 无作用域，M1 判不了）、
  **引擎既有赋值链宽松**（`x = (t)y + z = 1;` / `(int)` 版在改前也通过 ⇒ 单列的既有近似）、
  `tpc check` 对静默输入 `parse_ok=False` 却 `exit_code=0/syntax=[]` 的自相矛盾。
- **覆盖边界（2026-10-11 循环 #6）**：资格判定原本只在**块体语句位**（根块 / `is_block` 规则体）
  产生位点；**循环 #6 已把位点发现面扩到 production 层语句位**（`linter/discovery.py::
  _scan_container_sites`，`record=False` 只扫不建节点）⇒ C 函数体（`CompoundStmt`）与块内语句位
  **现已产生位点**（`void f(void){ x=(t)y; }` → 1 个 `eligible=true` (2,15)），且该扩展**零用户可见
  变化**（诊断 / `--json` / exit code 逐字节不变；对拍 0/144）。**raw 承载仍未做**（并入 M2+P4 原子批次）。
- **可达性与消费者现状（同上，实测）**：`eligible` 目前**零消费方**；默认路径 lint 阻断；`no_lint=True`
  时 `_stage_lint` 在 `if ctx.no_lint: return True` **之后**才收 `internal_warnings` ⇒ 位点表为空
  （`--no-lint` 不是入口）；`tpc check`（`analyzer/structure.py`）同样 blocking 短路。
- **位点匹配与区间（审计给出的判据形态）**：生效条件须 `eligible ∧ 精确 (line,col) ∧ 该 token 是语句
  元素起点`——"同行 `col ≥ site.col`"式 fallback 会把行/列漂移变成**错位消费**，应删；raw 消费区间
  **必须等于** linter `region`（与 `_stmt_ends`/`_block_ends`/`_derived_end_case` **单一来源**——P3 首次
  尝试曾自写 `derive_stmt_end_types`，已随回退删除）。
- **循环 #7 交付后的现状与已知偏差（2026-10-11）**：
  - **raw 承载 + M2 窄档 + P4 校验已落地**：`(myint)x` 在**顶层**与 **`CompoundStmt` 直接子语句**
    闭环（0 blocking + `success=True` + `_verbatim_text` 直出保真）；**安全网 = P4 的 analyze 校验**
    （遮蔽例被 `E002` 拒绝、不静默）。**理解路径已落地**（循环 #9，**两段协作**）：analyzer 段做
    语义二次确认 + 结构选定（结论挂 `raw_understand`；不一致报 `E003`，不与 `E002` 叠加），transform 段
    把候选提升为 `sub_node`（保留 `_verbatim_text` ⇒ 渲染仍直出）。**不变式**：渲染权威 = `_verbatim_text`；
    子树只是分析的确定结构，其显著 token 序列须与 verbatim 等价。**边界**：复合字面量 `(t){1}` 承载期
    建候选失败（不提升、不报错）；赋值链 `x=(t)y+z=1;` 也被提升（成功面不变，与既有宽松一致）。
  - **已知偏差（本批不做）**：① `x = (t)y + z = 1;`（gcc 判 `lvalue required`）现与 `(int)` 版
    **对齐放行**——引擎既有宽松，非本批引入；② `void f(int t);` 的**原型参数泄漏到文件作用域**
    （`t @ <global>`）⇒ "有全局 typedef 时的原型参数"会被 P4 误拒（修法在 `grammar/c/*.toml`
    的原型作用域声明）。
  - **一条引擎级陷阱（P1 曾被它害，值得记住）**：`transform/normalizer.py` 会把 `keyword.*` /
    `symbol.*` / `literal.*` 的 token 叶子抽成**字符串属性**（`StorageClass.base = "typedef"`）⇒
    任何"子树里含某 token **节点**"的判据在**生产口径**下失效（P1 因此把 typedef 全收成 `variable`，
    P4 误拒合法输入；而 P1 测试走的是未 normalize 的口径，**掩盖了它**）。现 C 包 `_api._subtree_has`
    已做成**跨形态判据**，并补了生产口径判据；"上移为引擎通用面"已登记 `TODO.md`。
- **性能**：真实语料 tv80_core（4755 行 / 2314 未收敛位点）`tpc lint` 由初测 **+13.7%** 经
  "段表 + 二分反查 + 前缀深度缓存"优化后回到 **+0.0%**（试解析本身不是热点，verilog 无 trial）。

## 成熟解法参照（见贤思齐）

- yacc/antlr 的 panic-mode/skip-to-sync 错误恢复——若要"一个语法错误后继续报更多错"，是参照
  方向；tpc 走"linter 前置单点 + 阻断"路线，职责已分给 linter，parser 保持纯。
- svlint/verible 对坏输入的诊断形态（`file:line:col: msg`）——linter 输出对齐参照，见
  `tests/e2e/eval_lint_accuracy.py`。

## 可实现性（若要改）

- parser 级恢复：需在 production 匹配失败处引入同步点集合（end_case/块结束），属引擎改动、
  收益有限——**当前无计划，接受现状**。
- linter 近似面收窄：随语法规则完善（`_stmt_ends` 推导）自动收窄，非独立任务。

## 关联条目

- `linter/linter_architecture.md`「已知边界问题」表（**多行 RHS 误报** / **`@*` 敏感列表误判**）
- lint recall 门禁：`tests/e2e/eval_lint_accuracy.py`
- 真实语料误报基线：`tests/e2e/eval_diag_baseline.py`
