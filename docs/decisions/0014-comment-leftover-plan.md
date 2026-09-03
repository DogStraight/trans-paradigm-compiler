# ADR-0014 — 注释遗留边界实施方案（ADR-0013 续作，draft）

Status: draft（未立项设计详案 = 下一 session 的接力起点；立项实现后升 accepted）

关联：ADR-0013（注释单机制，已实现）。本 ADR 承接其记录的三个遗留边界中
可立项的两个（① `(//RF` 行内容器头注释；② pratt op 行尾注释方向 B），
并固化**已探明的机制速查**——避免下个 session 重复源码考古（本次调研实测
消耗 ~30 分钟，结论不应再次蒸发）。

---

## 1. 背景与范围

ADR-0013 已闭环（b1bf8b2）。遗留边界（0013「已知边界」表）：
- ① 容器**开括号同行**的行内 line comment（`sub u (//RF interface\n .port...`；
  serv_top 55 条注释中唯一丢失的 1 条，L485）——行内形态，非独占行，
  B1/B1.3 窗口不收。
- ② pratt operator **行尾**注释（darkriscv `wire BMUX = ... || // bgeu\n ...`，
  5 条：bgeu/bltu/bge/blt/bne）——ADR 决策 5 边界；**作者已拍板方向 B**：
  挂后续 RHS 子节点行内/leading（机械安全：`//` 注释在重排表达式内必须
  位于输出行尾，只能随操作数独立断行）。
- ③ 宏展开行号漂移的 attachment 行尾注释（tv80/darkriscv 少数）——
  **维持边界不动**（根因在 preprocessor 反向映射，blast radius 大、ROI 低）。

## 2. 机制速查（勿重复考古；每行均为本次实测确认）

注释三通道现状（渲染端 restore 已纯 tpc——普通注释必须进树，否则丢）：
- **独立行注释 = Comment 子节点**（引擎 `_comment` 标记 + 派生节点名）；
  渲染：join.py 把 Comment 项 / item `sub_node` 首部 Comment 拆为独立行段
  （前后 Break）。
- **行内/行尾 = 节点 `_comment_slots`**：`inline_after`（{锚文本:
  [(注释,源行)]}，renderer line.py 遇布局含锚元素后插并删槽；join 消费
  锚=分隔符文本的条目）、`trailing`（node_renderer → LineSuffix 行尾）、
  `leading`（node_renderer → `Text(c)+Break()` 前置，已有实现）。
- 容器首元素前独占注释（B1.3，可用）：`try_plain_rule` 匹配成功后（行首
  开始 + `_repeat_iter_depth==0`）调 `_claim_head_comments`——领
  `_line_comment_anchors`（line 通道）中 `line_only` 且 `line < 规则末行`
  的条目，`sub_node.insert(0)` 挂 Comment 子节点，`_mark_comment_collected`
  从 line 通道移除（防外层规则双份）。
- 容器项间独占注释（B1，可用）：`_repeat_loop` 按行号窗口上浮为
  Comment 迭代项（窗口下界 = repeat 进入行；optional 不 lift）。
- 行尾注释通用路径：`parse_token` → `collect_following_comments`——注释后
  同行无代码 → `_record_anchor`(inline 通道 {anchor,text,line,type}) +
  `current_node._attached_comments`（node_renderer 视作 trailing）。**陷阱**：
  挂在会被 inline 化丢弃的包装节点（如 PortConnection）上 = 丢。
- pratt 表达式内注释：`_skip_gap_comments(tokens, idx, anchor, comment_sink)`
  ——operator 间隙：行中 → 返回收集，调用方 `_mount_op_comments` 挂
  BinaryOp/TernaryOp/UnaryOp `inline_after[op]`；行尾 → comment_sink
  （=丢）。parse_expression 入口前缀 while 同理 sink。注释「同行判定」：
  注释后跳过 comment/newline 找首个代码 token 比行号。
- 开括号 token 引擎级判据：`core/token_protocol.py` 有 `BRACKET_L_PREFIX =
  "bracket.l_"`（语言无关，勿硬编码具体类型）。
- 测试门禁：`tests/e2e/test_comment_restore.py` + `test_comment_container.py`
  + 既有 4 个注释测试文件；`run_all_tests.py normal/real`（保真缓存
  `.fidelity_cache.json` 单调、gitignored）；全量 `pytest -n 4`（`auto`
  会崩溃勿用）。

## 3. 方案 ①：`(//RF` → 容器 head Comment

- 现象根因：comment 与 `(` 同行 → 非 line_only，B1/B1.3 不领；
  collect_following_comments EOL 分支 → inline 通道 + 挂 PortConnection
  包装节点（`ModuleInst.ports` 只取 `$4.ports`，包装节点丢弃）→ 丢。
- **方案 A（推荐，改动最小）**：`_claim_head_comments` 增第二来源——
  `_comment_anchors`（inline 通道）中满足：非 tpc、`type` 以
  `BRACKET_L_PREFIX` 开头、`line < end_line` 的条目；同款挂 Comment 子
  节点（`sub_node.insert(0)`）；mount 后从 `_comment_anchors` 移除并记
  `_anchor_seen_inline`（防回溯重录 + 外层规则双份）。
- 效果：挂首个 NamedPortConnect（`.clk`/`.i_cnt_en` 行首、非 repeat 迭代
  项 → claim 合法）→ join 拆段 → 渲染 `(\n  //RF interface\n  .port...`，
  与 B1.3 独立行头注释同款。重解析后变独占行 → B1.3 再领，幂等。
- 风险（实测前先确认不劣化）：表达式括号 `f(// c\n x)` 同命中 → 若 x 在
  join 容器（参数表）渲染独立行、否则与现状一样丢（不劣化）；空端口组
  `(//c\n)` 由外层规则领挂错位——罕见，接受并记录。
- **勿改** `_is_line_only_comment` / `prepare_production` 全局语义（会撞
  B1 已上浮场景与 B1.2 删除回归）。

## 4. 方案 ②：pratt op 行尾注释 → 方向 B（后续 RHS leading）

- 语义（darkriscv 实测 1154-1158）：每行 `<条件> || // <指令名>`，注释标注
  当行条件片段（`// bgeu` 对应 `FCT3==7 && U1REG>=U2REG`）。渲染重排后
  行尾注释无安全落点 → 方向 B：挂**紧邻的后续 RHS 子节点** leading，
  输出强制断行 `...U2REG ||\n// bgeu\nFCT3 == 6 && ...`——机械安全
  （`//` 必在行尾）；语义近似（注释仍位于 op 与下段之间）。作者已拍板。
- 实现：`_skip_gap_comments` 增返回 EOL 注释列表（行尾分支不再只 sink）；
  BinaryOp 分支 RHS 解析后挂 `_comment_slots["leading"]` 于 right_node；
  TernaryOp 挂 true_val/false_val（对应 `?`/`:` 间隙）；UnaryOp 前缀挂
  operand。node_renderer leading 槽已有渲染（Text+Break 前置）。
- 动手前确认项：表达式子树经 ref → render_node（slot 生效路径）；leading
  硬 Break 在 group 内恒断行无异常；minimal 样例
  （`wire BMUX = A || // c\n B;`）输出 `A || // c\nB;` 形态正确。
- 复用参考：tv80/darkriscv 中 `? 2 : // misc errors` 形态现已在 expand
  场景存活（走既有行尾路径），勿回归。

## 5. 验证与收尾（每阶段）

1. 门禁：既有 4 注释测试 + test_comment_restore.py + test_comment_container.py；
2. `python tests/e2e/run_all_tests.py normal` 与 `real`（real 走 expand）；
3. serv_top 注释保留 55/55、darkriscv BMUX 5 条 + 全量保留不降
   （对比手段：probe 脚本比对源/输出注释文本，用完即删）；
4. 全量 `pytest -n 4` 全绿；
5. 本地 commit（不推送）；完成后 ADR-0013 已知边界表删除已闭环行 +
   CHANGELOG + TODO/ROADMAP 完成即删，本 ADR 升 accepted。

## 6. 本次调研遗留物清理

`probe_cmt.py` / `probe_ast.py` / `probe_ast2.py` / `probe_shapes.py`
（仓库根，未 commit）——已删或下 session 首删。
