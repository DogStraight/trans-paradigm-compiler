# 设计教训

> 非显而易见的语义 bug 和架构教训。
> 这里记录的不是"改了什么配置"，而是"为什么想错了"。

---

## 1. 双重反转：revert 方向处理

**日期**：2026-07-01  
**涉及**：`resolve_revert`（analyzer 钩子）+ `expand_typed_port`（transform 原语）

### 现象

`type spi { master: input miso, output clk; slave: revert master; }` 定义下，
`spi.slave spi_io` 展开为**全 output** 端口。

### 根因

两个模块各自做了一次"正确的"反转，组合后变成双重反转：

```
resolve_revert（analyzer 侧）
  视角：类型域内信号流
  逻辑："master 的 input → 作为 slave 就是 output"
  局部正确 ✓

expand_typed_port（transform 侧）
  视角：stored direction → Verilog 关键字
  逻辑："stored input → emit AnsiOutputDecl（硬编码 output）"
  局部正确 ✓

组合效果：
  原始: master input miso
  → resolve_revert: slave output miso        （第 1 次反转）
  → expand_typed_port: direction=="output"
    → emit AnsiInputDecl + direction="output"  （第 2 次反转）
  → renderer 输出 "output"
```

### 教训

**局部正确 ≠ 全局正确。** 两个模块各自在自己的边界内是合理的，但组合后的语义等价于双重反转。修复后改为直通——stored direction 已经是模块/角色的正确 Verilog 方向，不需要再反转。

### 如何避免

端到端数据流验证：对"数据经过 N 个模块，每个模块做一次变换"的管线，必须准备一组完整输入→预期输出用例，覆盖所有模块组合路径。单模块单元测试不够。

---

## 2. 符号注册时机：先 scope 还是先 symbol

**日期**：2026-07-01  
**涉及**：`_walk_node`（semantic_analyzer.py）

### 现象

`type spi { ... }` 定义的 `spi` 类型名，在 `TypedTypeSpec` 中 `identifier_ref = "type_name"` 解析时找不到。

### 根因

`_walk_node` 中先推入新作用域（scope），再注册符号（symbol）。导致类型名 "spi" 的 symbol 被注册到 TypeDecl 自身创建的新作用域中，而不是父作用域。`TypedTypeSpec` 沿作用域链向上查找时找不到。

### 教训

scope（作用域）和 symbol（符号）是不同概念。scope 创建命名空间，symbol 登记可查找的条目。在作用域推入**之后**注册的符号属于新作用域内部，对外不可见。

修复：交换顺序——先注册 symbol 到当前作用域，再推入新作用域。这样类型名在父作用域可见，同时不影响类型体内部的作用域隔离。

### 如何避免

涉及 scope + symbol 同时存在的规则，必须明确：
1. symbol 属于哪个作用域？（当前 scope vs 新 scope）
2. 谁需要 resolve 这个 symbol？（外部引用者 vs 内部子节点）
3. 画出 scope 树 + symbol 位置再实现
