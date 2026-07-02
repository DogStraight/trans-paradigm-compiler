# 声明式错误恢复（`recovery` 字段）

## 改动范围（2026-07-02）

### 引擎层

| 文件 | 改动 | 类型 |
|------|------|------|
| `parser/production_matcher.py` | `match_productions` 中 `committed` 默认值从 `after is None`（True）修正为 `False`，同时错误恢复吞行时如果目标 token 类型可以在该 token 上停止并消费它 | 🐛 修复 |
| `parser/block_parser.py` | `parse_block_body` 遇到 `end_token` 时不再 `advance_token()`，改由调用方 production 消费 | 🐛 修复 |
| `renderer/primitives/ref_prim.py` | `eval_ref` 渲染 `ref` 后检查父节点 `_error` 属性，有则用 Error 布局追加渲染 | ✨ 新功能 |
| `renderer/renderer.py` | 添加 `_get_merged_layout()` 方法及缓存 `_merged_layout_cache` | ⚡ 优化 |
| `renderer/node_renderer.py` | `render_body` 中布局合并走 `_get_merged_layout` | ⚡ 优化 |
| `renderer/primitives/join_prim.py` | 同上 | ⚡ 优化 |
| `core/define.py` | `GrammarRule._KNOWN_FIELDS` 未变动（`recovery` 通过 `rule.parser` dict 存取） | — |

### TO M L 配置层

| 文件 | 规则 | 改动 |
|------|------|------|
| `00_blocks.toml` | Root, ModuleBlock, ProcBlock, TaskBlock | 添加 `recovery = { strategy = "consume_line" }` |
| `00_blocks.toml` | ModuleBlock | 添加 `end_case = ["keyword.endmodule"]` |
| `00_blocks.toml` | ProcBlock | 添加 `end_case = ["keyword.end"]` |
| `00_blocks.toml` | TaskBlock | 添加 `end_case = ["keyword.endfunction", "keyword.endtask"]` |
| `00_blocks.toml` | Error | layout 改为 `{ line = ["/* ERROR: ", { ref = "raw" }, " */"] }` |
| `00_blocks.toml` | 三处 `entry = "..."` | 删除（解析器不消费的无效配置） |
| `01_module.toml` | PortParens | 添加 `recovery = { after = "bracket.l_parentheses" }` |
| `10_if.toml` | IfBlock, IfStmt | `recovery = { after = "keyword.if" }` |
| | ElseIfBlock, ElseIfStmt, ElseBlockBranch, ElseBranch | `recovery = { after = "keyword.else" }` |
| `03_always.toml` | AlwaysBlock | `recovery = { after = "keyword.always" }` |
| `20_for.toml` | ForLoop, ForLoopBlock | `recovery = { after = "keyword.for" }` |
| `40_case.toml` | CaseStatement | `recovery = { after = "@CaseKeyword" }` |
| `30_assign.toml` | AssignStatement | `recovery = { after = "keyword.assign" }` |
| `50_func_task.toml` | FuncDeclANSI, FuncDeclOld | `recovery = { after = "keyword.function" }` |
| | TaskDeclANSI, TaskDeclOld | `recovery = { after = "keyword.task" }` |
| `70_misc.toml` | GenerateBlock | `recovery = { after = "keyword.generate" }` |

## 设计原则

1. **`recovery` 是声明式描述**：只声明"这个规则在出错时能恢复多少信息"，不写恢复的具体逻辑
2. **没有 `recovery` = 严格回溯**：`committed = False`，和以前一样零侵入
3. **策略独立**：Block 级和 Production 级策略互不依赖，可以混合使用

## 两层恢复机制

| 层级 | 字段 | 效果 |
|------|------|------|
| **Block 级** | `strategy = "consume_line"` | 块内一句匹配失败时，吞掉整行，块继续 |
| **Production 级** | `after = "keyword.xxx"` | 产生式列表中该 token 匹配成功后视为"已提交"——后续任意元素失败时不回溯，产 ErrorNode |

### Block 级示例

```toml
[ModuleBlock.parser]
end_case = ["keyword.endmodule"]
recovery = { strategy = "consume_line" }
```

### Production 级示例

```toml
[IfBlock.parser]
production = [
    "keyword.if",          # ← after 提交点：匹配后 committed = True
    "bracket.l_parentheses",
    "@Expression",
    "bracket.r_parentheses",
    "@BeginEnd",
    "@ElseChain?",
]
end_case = ["newline", "keyword.end", "keyword.else"]
recovery = { after = "keyword.if" }
```

`after` 在 `keyword.if` 匹配成功后设 `committed = True`。此后 `@Expression` 出错时不回溯，产 ErrorNode。`@Expression` 本身不设 `recovery`，所以它内部还按严格回溯执行。

## 三层 Error 恢复覆盖示例

输入：
```verilog
module top (bad input clk);
    rstn
    reg counter;
    wire flag;
endmodule
```

输出：
```verilog
module top(/* ERROR: bad input clk */);

    /* ERROR: rstn */
    reg counter;
    wire flag;
endmodule
```

对应 AST：

```
Root
└── ModuleDecl
    ├── module_name: "top"
    ├── ports: PortParens
    │   └── _error: Error "bad input clk"   ← ① PortParens 生产级恢复
    ├── body: ModuleBlock
    │   ├── Error "rstn"                    ← ② ModuleBlock 块级恢复
    │   ├── RegDecl "counter"               ← ③ 正常解析
    │   └── WireDecl "flag"                 ← ③ 正常解析
    └── endmodule
```

## 常见问题

### Q: 为什么 `_error` 是属性而不是子节点？

`_error` 所在节点本身有有效内容（如空的端口列表 `top()`），错误是附属信息。body 中的 `Error` 节点是整行无效的产物。两种错误语义不同，渲染上已统一为 `/* ERROR: ... */` 格式。

### Q: 哪些规则不适合加 `after`？

以 `@Identifier` 开头的规则（如 `NonBlockingAssign`、`BlockingAssign`、`ModuleInst`、`SubroutineCall`）没有唯一关键字锁定身份，提交过早会误判。这类规则的错误恢复依赖 Block 级 `consume_line`。
