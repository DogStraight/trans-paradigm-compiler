# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## P1 — Verilog 实例完善

### P1.5 已知缺陷收尾

- [ ] **注释落在 `inline = true` 规则内 / 行尾型且紧跟 token 时被丢**（既有边界，
      2026-09-17 三方向评估发现，**非本轮引入**；两例实测均**丢内容**）：
      - ① `wire a = /* c */ b;`（行中块注释，wire 声明）——注释由
        `collect_following_comments` 挂到 `Init` 节点的 `inline_after`，而 `Init`
        声明 `inline = true` → 规则节点被弃（`_try_inline_rule`），槽随节点消失
        （`assign` 语句不受影响，故既有断言 `test_midline_embed_in_place` 未拦住）。
        拟修：inline 展开时**迁移注释槽**到替身节点，并让行中槽在 inline 规则下用
        `inline`（前置同行）语义而非锚 token（锚不在替身节点布局里）。
      - ② `wire a = // why` 换行接右操作数——注释非行中、非独占行（行尾型），由
        `collect_following_comments` 只登记 inline 锚（普通注释不回插）→ 丢。
        拟修：该分支对行尾型挂 `trailing`（LineSuffix 随行尾），独占行型仍留给
        容器/闸门通道。
      两处都需过 darkriscv 注释零丢/零重与全量门禁（参照本轮“注释文本零丢失零重复”盘账）。
