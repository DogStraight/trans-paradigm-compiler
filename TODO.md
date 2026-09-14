# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## 0.1.2 目标（2026-09-11 立项，单轨：宏体入树 → 管线时点化）

> 设计：宏体入树（机制见 `preprocessor/README.md`）+ 时点化/可视化/契约校验
> （机制见 `pipeline/README.md`）。
> 每阶段独立验证、门禁通过才进下一阶段；阶段完成即删本行。不含：C 语言包（松散活动，
> 不立项）、P3.2/P3.4 增量、P3.5 Rust 下沉、P4 多后端。
> **版本节奏（作者定 2026-09-14）**：0.1.1 = 9 月内发布（发布材料已备：
> CHANGELOG 归拢 09-09 + tag `v0.1.1`；剩余发布动作按需执行）；**0.1.2 = 10 月
> 版本**——本批次工作已全部完成于主分支（阶段 0-9），等 10 月发布窗口，勿催。

- [ ] 阶段 6 收尾 — 中间产物可视化：剩 transform 侧更多插件自述（出口已具备，
      按需补）

## 文档工程（2026-09-04 立项，使用复盘 6 类文档框架）

- [ ] **术语表（glossary）**：Doc IR / pass / slot / postpass / capability /
      world A·B / inject / fragment 等术语集中定义（文档工程对标遗留，中低成本；
      落点待定：docs 教程层或独立文件）

## P1 — Verilog 实例完善

### P1.5 已知缺陷收尾

- [ ] **darkriscv 条件编译嵌套位置精度（宏展开路径还原残余）**：ifdef 已
      101/101 全还原、无占位残留、lint 零诊断；残余 = 表达式链内相邻条件块
      （IFPC 三目链的 EBREAK/INTERRUPT/DBNZ）还原位置依赖插值定位（渲染行距
      非线性 + 锚点稀疏），嵌套位置仍有偏差 → sv-parser 预处理仍拒（interop
      豁免保留，见 `tests/e2e/test_real_corpus.py::_SVPARSER_INTEROP_SKIP`）。
      根治需 active 内容 marker 化（_flush_block 改造）或 token span 映射
      （P3.1 已落地，前置就绪）。
