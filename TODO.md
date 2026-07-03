# TODO

## 错误恢复

- [ ] **测试覆盖严重不足** — 当前 4 个 errors 测试全部 FAIL（因 `--recovery` 默认关闭），实际恢复能力无人知晓
  - 需要按策略编写独立测试：skip_to_end / skip_one / skip_to_matching / skip_to_newline / skip_then_retry_until
  - 需要测试 committed 传播 + end_case_chain 的同步边界
  - 需要测试 global_recovery 三层开关的行为
  - 需明确：恢复能力到底到什么程度？哪些场景能恢复、哪些不能？