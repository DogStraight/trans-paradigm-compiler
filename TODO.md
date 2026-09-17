# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## P1 — Verilog 实例完善

### P1.5 语言形态外置收尾（两处字面量 → 宏策略能力，见 ROADMAP P3.6）

形态清单与已外置项见 `preprocessor/README.md`「形态清单」；展开策略已迁为语言包
能力 `[capabilities] macro_policy`。剩两处引擎侧字面量，各有前置条件：

- **宏调用参数定界符**：`_match_paren_args` / `_split_args` 写死 `(` `)` `,` 与
  嵌套 `[` `]`（可随宏策略能力传语言函数，或声明为"调用括号对 + 实参分隔符 +
  嵌套括号表"）。当前只有 verilog 声明宏形态（c4/yaml 无 `[macro_recognition]`）
  → 影响面窄。
- **宏调用后随位宽字面量后缀**：`_LITERAL_SUFFIX_RE`（`'s`/进制/digit 集）与
  `[[number.based]]` 是同一知识的两处表达。**不能直接改为 FSM 探测**：该正则
  刻意比数字声明宽（还要覆盖 SV 填充字面量 `'0`/`'1`）——先补声明面（或加
  "宽一档"的声明字段）再改，否则丢还原区间。
