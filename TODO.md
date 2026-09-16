# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## P1 — Verilog 实例完善

### P1.5 已知缺陷收尾

- [ ] **条件块还原：端口表内 `ifdef` 组位置漂移（1 处，2026-09-17 探查留存）**：
      darkriscv 端口表内 `ifdef __INTERRUPT__` 组（源在 `RES` 之后）被还原到
      `IDREQ` 之后——属被 production skip 吞掉、需插值定位的 5 个占位之一。
      逗号/token 完整、sv-parser 接受（interop 已回门禁），属位置保真残余而非
      语法缺陷。根治 = active 内容 marker 化（`_flush_block` 改造）或 token
      span 映射（P3.1 已落地，前置就绪）。
- [ ] **扁平列表内「项间行注释」吞后续项（布局语义，2026-09-17 留存）**：列表被
      布局扁平化（单行）且某项行尾是行注释时，同行后续项被并入注释（`module
      m #(...)( input a, // c output b);`）。末项已修（收尾护栏，声明驱动，见
      `renderer/primitives/join.py`），项间未修——硬换行会破坏 group 软/硬混排
      （实测退化为「首项贴 `module x(`+ 余项另起」并扰动布局断言）。根治需
      布局层「含硬换行 group 必断」语义（propagate breaks），波及面大，另立。
