# ADR-0026: 片段模式 = 语法配置驱动的岛式分片（全域岛 / 零声明面）

- Status: accepted
- Date: 2026-10-30

## 背景

完整 SystemVerilog 语法写不出来、写出来性能也差；真实需求是"只写关心的部分语法，
其余文本原样保留"。P0 用显式记号 + 手写一条 `always @(*)`→`always @*` 规则验证了
"纯文本片段可独立改"的安全边界，但把"改写规则集合/岛声明"当成了骨架；实测正式管线
并不做该改写，规则与管线脱节。

调研（`docs/references.md`「岛式分片 / 部分解析」）显示成熟做法（island grammars、
tree-sitter included ranges、Black/clang-format 范围格式化、comby）的共性是：边界在
文本/词法层判定，岛内用真实工具，安全靠标记契约 + 后验。

## 决策

1. **岛由语法配置推导**：片段模式下，语言包 TOML 推导出的语法单元（`is_statement` /
   `is_block` 规则 + 块起止 + 发现层切分）默认就是岛——**不设 `[[island_rules]]`
   声明段、不设 `island_rewriter` 能力位、不设记号/范围可选模式**。要限定"只有某部分
   语法有效"，单开一个语言包。
2. **推导层归属**：复用 `linter/` 内部的推导组件（`discovery`/`lookahead`/
   `grammar_slicer`/`first_set`/`discovery_shape`），不另建顶层包；`islands/` 只做
   "分片 → 管线 → 合成"。
3. **处理模型**：自顶向下——节点文本进真实管线成功 ⇒ 整段替换、不再处理子节点；失败
   递归子节点；仍失败 ⇒ water 原样保留。含宏/指令行的节点整体落水（展开会改原文）。
4. **后验默认开**：岛级重解析 + 双跑逐字幂等；无岛/零变化逐字节返回原 bytes
   （BOM/CRLF/无尾换行保真）；不提供跳过开关。
5. 片段模式是**独立命令**（`tpc fragment`），不改 `format`/`lint` 等既有命令默认行为。

## 权衡

- 放弃"按记号圈定范围"的显式控制：换来零配置面与"写了哪部分语法就处理哪部分"的直觉；
  需要更窄作用域时用独立语言包（作者 2026-10-30 定）。
- 每个岛跑一次真实管线 + 后验（双跑）：比全文件单遍慢，但这是"只处理能处理部分"的
  代价；P2 再评估并行/增量。
- 岛内默认只跑 parse+render（不跑 analyze/transform）：岛缺岛外上下文，语义级变换须
  显式开启并另有判据（P2）。
- 被拒绝的备选：隐式关键字锚点自动发现（P1 先不做，等边界判据有实测数据）；第二套
  轻量改写规则（与真实管线脱节，P0 已证伪）。

## 验证

- `tests/engine/test_islands.py`：identity（无岛/未知构造/BOM+CRLF）、岛处理、
  water 保留、宏落水、双跑幂等、C 包同机制。
- 真实语料：`tpc fragment` 对 `tests/e2e/samples` 抽样跑无崩溃、输出可再次改写一致；
  water 区间逐字节不变（含宏/未知语法的负例）。
- 既有命令零影响：`format`/`A-B` 行为不变（片段模式独立入口）。

> Impl: islands/model.py · islands/segment.py · islands/process.py · islands/splice.py · islands/rewrite.py
> Test: tests/engine/test_islands.py
