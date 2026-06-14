# AST 规范化规范 (Canonical AST Specification)

## 目标

定义 **Parser 原始输出**经过 `normalize_ast()` 变换后的规范 AST 结构。
Renderer 仅依赖此规范形式，不感知 parser 内部实现细节。

## 被消除的节点类型

以下 parser 内部节点在规范化后**全部消失**：

| 节点类型 | 变换规则 |
|---------|---------|
| `keyword.*`（如 `keyword.input`） | 提取 `.value` 为字符串，设置到父节点属性 |
| `symbol.*`（如 `symbol.base.comma`） | 同上 |
| `id` | 同上 |
| `optional`（空） | 删除对应属性 |
| `optional`（有子节点） | 展开，子节点替换 optional 的位置 |
| `repeat` | 展平为列表（子节点依次排列） |
| `sequence` | 展平为列表（仅保留 Node 子项，过滤分隔符） |
| `Block` | 通过 `body_role = "flatten"` 展开到父节点 `sub_node` |

## 规范 AST 结构

### 通用规则

1. **`sub_node`** — 所有"主体"子节点的容器。body 语句、列表项等都在这里。
   - 始终是 `list[Node]`（保证存在，可为空）
2. **命名属性** — 语义子节点通过具名属性引用。
   - 如 `ModuleDecl.module_name` → 字符串 `"traffic_light"`
   - 如 `PortDecl.direction` → 字符串 `"input"` 或 `"output"`
   - 如 `Range.msb` → `BinaryOp` 节点（表达式）
3. **无冗余属性** — `first`、`rest`、`body`（Block 包装）等已被删除。

### 节点类型清单

#### Root
```
Root.sub_node = [ModuleDecl, ...]
```
Root 的 `sub_node` 包含所有顶层模块。

#### ModuleDecl
```
ModuleDecl {
    module_name: str          # 模块名
    params: ParameterList?    # 参数列表（或 None）
    ports: PortList?          # 端口列表（或 None）
    sub_node: [RegDecl | WireDecl | LocalParamDecl | AlwaysBlock | ...]
}
```
`body` 属性已被删除，其子节点已提升到 `sub_node`。

#### PortList
```
PortList {
    sub_node: [PortDecl, ...]   # 端口声明列表
}
```
`first`/`rest` 属性已被合并到 `sub_node`。

#### PortDecl
```
PortDecl {
    direction: str     # "input" | "output" | "inout"
    port_type: str?    # "wire" | "reg" (或 None)
    range: Range?      # 位宽（或 None）
    port_name: str     # 端口名
}
```

#### RegDecl
```
RegDecl {
    range: Range?      # 位宽（或 None）
    reg_name: str      # 寄存器名
}
```

#### WireDecl
```
WireDecl {
    range: Range?      # 位宽（或 None）
    wire_name: str     # 线网名
}
```

#### Range
```
Range {
    msb: Node          # 高位表达式
    lsb: Node          # 低位表达式
}
```

#### LocalParamDecl
```
LocalParamDecl {
    sub_node: []       # 无主体
    items: LocalParamItemList   # 参数项列表（通过 layout.source 引用）
}
```

#### LocalParamItemList
```
LocalParamItemList {
    sub_node: [LocalParamItem, ...]   # 参数项（first/rest 已合并）
}
```

#### LocalParamItem
```
LocalParamItem {
    param_name: str
    value: Node        # 表达式
}
```

#### AlwaysBlock
```
AlwaysBlock {
    sensitivity: SensitivityList?   # 敏感列表
    body: Statement                 # 语句体
}
```

#### SensitivityList
```
SensitivityList {
    sub_node: [EdgeSense | str, ...]   # EdgeSense 节点或 "*" 字符串
}
```

#### EdgeSense
```
EdgeSense {
    edge: str        # "posedge" | "negedge" (或空)
    signal: str      # 信号名
}
```

#### IfStatement
```
IfStatement {
    condition: Node     # 条件表达式
    then_stmt: Statement
    else_chain: ElseChain?
}
```

#### ElseChain → ElseIf | ElseBranch
```
ElseIf {
    condition: Node
    body: Statement
}
ElseBranch {
    body: Statement
}
```

#### CaseStatement
```
CaseStatement {
    expr: Node            # case 表达式
    sub_node: []          # 空（主体通过 items 引用）
    items: CaseItemList   # case 项（通过 layout.body.source 渲染）
}
```

#### CaseItemList
```
CaseItemList {
    sub_node: [CaseItem | DefaultItem, ...]   # first/rest 已合并
}
```

#### CaseItem
```
CaseItem {
    value: Node      # 标签表达式
    stmt: Statement  # 语句
}
```

#### DefaultItem
```
DefaultItem {
    stmt: Statement
}

#### Statement (包装节点)
```
Statement {
    stmt: Node    # 指向实际语句节点
}
```

#### BinaryOp
```
BinaryOp {
    op: str          # 运算符字符串 ("+", "-", "==", "&&", ...)
    left: Node       # 左操作数
    right: Node      # 右操作数
}
```

#### UnaryOp
```
UnaryOp {
    op: str           # "!" | "~"
    operand: Node     # 操作数
    position: str     # "prefix" | "postfix"
}
```

## 与旧 optimizer 的对比

| 功能 | optimizer | normalize_ast | 说明 |
|------|-----------|---------------|------|
| keyword 提取 | `extract_keyword_value` | 内置 | normalize_ast 在递归中自动处理 |
| id 提取 | `extract_id_value` | 内置 | 同上 |
| optional 展开 | `flatten_optional` | 内置 | normalize_ast 返回 None 而非 [] |
| repeat/sequence | `flatten_repeat_sequence` | 内置 | normalize_ast 的 sequence 过滤分隔符 |
| first/rest | `flatten_first_rest_list` | 内置 | normalize_ast 合并到 sub_node |
| Block 展开 | `flatten_block` | `body_role` | normalize_ast 通过 TOML 配置控制 |
| Root 展开 | `flatten_root` | 无 | Renderer 的 Root layout 处理 |

**差异说明**：
- optimizer 将 `optional` 展开为 `[]`（空列表），normalize_ast 展开为 `None`（删除属性）
- optimizer 将 `first/rest` 替换为平列表（替换原节点），normalize_ast 保留原节点但填充其 `sub_node`
- normalize_ast 的 `body_role` 是配置驱动的，optimizer 的 `flatten_block` 硬编码
