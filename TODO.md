# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## P1 — Verilog 实例完善

### P1.5 已知缺陷收尾

- [ ] **条件块还原：端口表内 `ifdef` 组位置漂移（1 处，2026-09-17 探查留存）**：
      darkriscv 端口表内 `ifdef __INTERRUPT__` 组（源在 `RES` 之后）被还原到
      `IDREQ` 之后——属被 production skip 吞掉、需插值定位的 5 个占位之一。
      token 完全、sv-parser 接受（interop 已回门禁），属位置保真残余而非
      语法缺陷。根治 = active 内容 marker 化（`_flush_block` 改造）或 token
      span 映射（P3.1 已落地，前置就绪）。
