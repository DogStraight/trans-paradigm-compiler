# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## P1 — Verilog 实例完善

### P1.5 已知缺陷收尾

- [ ] **darkriscv interop 失败（探查 2026-09-17：原「条件块嵌套位置精度」归因证伪）**：
      sv-parser 接受原始源（exit 0）、拒 tpc 输出；真因两条，均与条件块无关 ——
      ① **formatter 二次格式化还原后文本**（restore 之后 `format_generated`）：
      `` `__THREADS__ `` 等指令被当普通 token，声明被打散成
      `reg IFPC // 注释 [0:...]-1] stage`（`;` 落进注释）→ 报 630；
      ② **renderer 端口表收尾 `);` 与末项同行**，被末项行尾行注释吃掉
      （源 685 `);` 独占行 → renderer 输出 `... :));`）→ 报 560；默认
      `format_output=true` 时②被 formatter 掉手掩盖。
      条件块位置残差实测很轻：157 占位 = 118 独占行精确命中 + 36 嵌套（多轮扫描
      还原）+ 3 行内 + **0 丢失**；渲染文本原生 marker 116，仅 5 个被 production
      skip 吞掉需回插（4 插值 + 1 相邻跟随）；关 formatter 后还原文本 == 最终输出
      （相似度 1.0000），IFPC 三目链 token 序列与源侧一致；真实位置偏差仅 1 处
      （端口表内 `ifdef __INTERRUPT__` 组被挪到 IDREQ 之后）。
      → 修 ①② 后重跑 interop，再评估 active 内容 marker 化 / token span 映射
      是否仍需做（原与路线选择挂钩的前提已不成立）。
