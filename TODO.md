# TODO

## 错误恢复（已否决）

解析器引擎架构（回溯递归下降 + 配置驱动）与错误恢复不兼容。
详见 [docs/recovery.md](../../docs/recovery.md) 作废说明。

- 调研结论：Tree-sitter（GLR LR 表）、ANTLR（ATN 编译）、MoonBit（手写 sync 栈）
  都依赖"当前状态 × 当前 token"的查询能力，我们的引擎没有编译阶段无法提供
- 替代方案：当前仅做更精确的错误消息（ParseError 上下文），不做 Token 级恢复
- 遗留：4 个 errors 测试用例（error_garbage / error_garbage2 / error_missing_semicolon / error_extra_begin）
  需要评估是删除还是重写为"解析失败测试"