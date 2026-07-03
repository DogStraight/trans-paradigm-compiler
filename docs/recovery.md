# 声明式错误恢复（`recovery` 字段）

## 概述

错误恢复通过 TOML 规则的 `recovery` 字段声明。有两种形式：

```toml
# 形式 1: 布尔值 — 启用默认恢复（skip_to_end）
recovery = true

# 形式 2: 字典 — 按 $N 路径指定恢复策略
recovery = { "$3" = "skip_to_matching" }
```

未设置 `recovery` 的规则行为不变（严格回溯）。

## 恢复策略

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| `"skip_to_end"`（默认） | 双路径同步扫描：同步到后继产生式起始 / 当前产生式自然结束 / 规则 end_case 边界 | 通用语句级恢复 |
| `"skip_one"` | 只跳过当前一个 token，不向前扫描 | 原子规则、标识符 |
| `"skip_to_matching"` | 括号感知扫描：维护嵌套深度，遇到匹配的关闭括号时停止 | 端口、块、括号包裹的结构 |
| `"skip_to_newline"` | 跳到下一个换行，吞掉本行剩余内容 | 语句级恢复 |

## 路径语法

key 使用 `$N` 语法（与 attribute_binder 一致），1-based：

```toml
[PortParens.parser]
production = [
    "bracket.l_parentheses",     # $1
    "@PortList?",                # $2
    "bracket.r_parentheses",     # $3
]
recovery = { "$3" = "skip_to_matching" }
```

子元素寻址（choice 的替代索引、seq 的项索引）：

```toml
recovery = { "$2.$1" = "skip_one" }
```

## 全局开关

```python
parser = Parser(global_recovery=True)  # 全局启用 recovery
```

`global_recovery=False` 时忽略所有 TOML 的 `recovery` 标记。

## 引擎架构

```
_try_production()  →  检查 committed
    ↓ 失败 + committed
_find_recovery_strategy()  →  查 recovery 字典
    ↓
策略分派: skip_to_end / skip_one / skip_to_matching / skip_to_newline
    ↓
ErrorNode(raw=第一个坏 token) + 消费 token 到同步点
```

路径通过 `context._recovery_path` 逐层传递：

```
_try_production          设置 "$3"                    (production[2] 1-based)
  └─ _parse_choice       扩展 "$3.$1", "$3.$2"        (choice 替代索引)
      └─ _parse_call     失败时查 _recovery_path → _try_recovery_by_path
```

## 括号映射

括号配对从 `base/token.toml` 的 `[bracket] pairs` 定义加载，在 `Parser.__init__` 中初始化为 `self._bracket_map` / `self._inverse_bracket_map`。
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
