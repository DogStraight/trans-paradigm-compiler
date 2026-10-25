# Gap — parser 回溯成本与 atom 位置级 memo（主线 2 块 2）

- 状态：**块 2 收口（#68/#69，2026-10-23）**：atom 位置 memo + 规则级 FIRST 早拒；cJSON **57.6s → 2.98s（median）**、C 语料门禁 **20.3–23.0s**；A/B 0/144、全量 4377/14、7/7 0 诊断、pyright 0。
- 关联：`PROGRESS.md` 块 2；`TODO.md`「C 真实语料解析回溯成本」；`tests/e2e/eval_diag_baseline_c.py`
- 参照：`docs/gaps/gap-parser-linter-approximation.md`（parser 无错误恢复为刻意接受）；linter packrat 记忆化先例

## 现状实测（当前 HEAD）

| 指标 | 数值 |
|---|---|
| cJSON.c 解析（expand 后 19,537 token） | **58.7s**（仅 parse；expand 0.45s） |
| `_try_plain_rule` 总尝试 | **4,167,446**；unique(rule,pos) **225,874** ⇒ 重复率 **18.45x** |
| 最热位点 | L1380 `buffer`：14 个 atom 规则各被尝试 **4096 次**（2¹²，嵌套括号层数） |
| C 语料门禁（7 文件） | ≈90–110s |

**成因**：atom 匹配器对每个操作数按 production 长度降序尝试全部 14 个 atom 规则，取
消费最多者；`ParenthesizedExpr`、`PostfixExpr`(→`PrimaryExpr`→`ParenthesizedExpr`)、
`CastExpr` 等对同一 `( … )` 会**各自递归重解析内层表达式** ⇒ 每层嵌套乘一个因子，
嵌套 k 层即 2^k。根因不是语法歧义（`int a b;` 那种过接受另案），而是**同一位置被重复
求值**；普通表达式链（`a+b`）不受影响，长嵌套括号/成员链放大。

## 原型证据（仅 monkeypatch，未改动工作树）

- 在 `_atom_parser_impl` 外层加 **按 `idx`（token 位置）缓存 `(node, consumed)`**，
  同一 parse 内命中直接复用：
  - cJSON parse：**58.7s → 7.04s（8.3x）**；AST 节点名序列 SHA1 **完全一致**（25,230 节点）。
  - C 语料门禁（7 文件）：**90–110s → 28.6s**（已达 ≤30s 目标）；7/7 `parse_ok`、0 诊断。
- 已知未验证：缓存命中复用**同一 Node 对象**——需核验 attrs/注释槽/路径计数是否有
  上下文依赖；作用域门控（`requires_symbol`）与声明回滚期间的位置也可能改变结果。
  故原型只作可行性证据，不当结论。

## 实施记录（#68）

- `_atom_parser_impl` 已按 `(token 位置, 作用域版本)` 缓存 atom 结果；`_ScopeStack` 增加 `version`（register/restore/push/pop 仅在真实状态变化时 +1）；`Parser.parse` 每次清空 memo；`restore` 增加无变化快速路径。
- 同机对照：pre-memo 57.6s → 8.75s（median，6.6x）；AST 节点名序列 SHA1 与改前一致（25,230 节点）；全量 4377/14、A-B 0/144、门禁 7/7 0 诊断；`COG|_atom_parser_impl` 以性能分支理由进 `tools/baselines/structural_kept.json`。
- 剩余：直接成本仍 ~8–9s；继续优化需降候选/热点开销（见下）。

## 收口记录（#69）

- 在 `try_plain_rule` 增加规则级早拒：`follow.compute_first_map` 给出完整 FIRST+nullable；`build_rule_first_map` 只收非块/非 pratt、非 nullable、FIRST 非空的规则；当前 token 不在 FIRST 且非 trivia/宏/占位豁免 ⇒ 直接失败（不建节点/日志/帧）。
- 结果：cJSON median **2.98s**（较 pre-memo 57.6s **19.3x**）；门禁 median ~21s（含 linter 等全阶段）；A/B 0/144；全量 4377/14；corpus 7/7 0 诊断；S Δ0。
- 累计手段：atom 位置 memo（#68）+ 规则级 FIRST 早拒（#69）；未改 AST（节点名序列 hash 一致）。

## 后续（非块 2）

1. 在 `Parser` 内实现**每 parse 清空**的 atom 位置 memo：
   - 键 = `(start_ptr, state_token)`；`state_token` 至少含作用域栈版本/深度（门控规则需要），
     必要时含注释队列代际；
   - 仅缓存**无副作用**的 atom 规则结果；含 `requires_symbol` 的门控分支按 state 区分；
     命中若存在 Node 共享风险，则回退为"缓存 consumed + 命中重放"或深拷贝。
2. 若 7s 仍不达 5s：追加 **atom 候选去重**（如无后缀时不重复尝试 `PostfixExpr` 与
   `ParenthesizedExpr`；按首 token 预筛但**保留宏/占位兜底**——此前 FIRST 预过滤因
   verilog 回归已回退，不重蹈）。
3. 判据：cJSON ≤5s；门禁 ≤30s；A/B **0/144**；corpus 7/7 0 诊断；全量 tests 绿；
   render/幂等/注释测试绿；AST 签名（节点名+标量 attrs+span）与改前逐条一致。
4. 止损：若 memo 引入 Node 共享导致注释/路径回归且深拷贝后仍不达 2x ⇒ 改走候选去重路线；
   两条都失败则登记实测瓶颈并保留旧行为，不强行改语义。

## 不做 / 已否

- **atom FIRST 预过滤**（#51 前实验）：cJSON 62→47s 但 verilog 真实语料 parse 回归（模块 0）；
  已回退，不再作为主路线（可作为余量优化，但必须带宏/占位 FIRST 兜底）。
- **全量 packrat**：parser 写状态（符号注册/注释簿记/路径计数）且失败记忆化曾因
  `sibling_counter` 回退；只做 atom 局部 memo，不做全规则 packrat。
