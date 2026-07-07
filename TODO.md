# TODO

## 错误恢复（已否决）

解析器引擎架构（回溯递归下降 + 配置驱动）与错误恢复不兼容。
详见 [docs/recovery.md](../../docs/recovery.md) 作废说明。

- 调研结论：Tree-sitter（GLR LR 表）、ANTLR（ATN 编译）、MoonBit（手写 sync 栈）
  都依赖"当前状态 × 当前 token"的查询能力，我们的引擎没有编译阶段无法提供
- **替代方案**：`lint/` — 共享语法的轻量错误扫描器
  - `LinterScanner.scan(source)` → `list[LintDiagnostic]`
  - LSP Diagnostic 格式输出（`--json`），可直接接入 VS Code
  - 核心：复用 Parser 的 `parse_sentence`，失败记错 + 跳到 `;`/block_end 继续
  - 表达式错误直接推给 Pratt，整块标记
  - 当前：26/30 normal 无误报；4 个宏文件因未展开 `` `define `` 报错（预期）
- 遗留：4 个旧 errors 测试用例可转为 linter 测试