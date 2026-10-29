# structure — 语法配置驱动的语言无关结构推导层

> 把语言包 TOML 规则推导成**可消费的分片/结构信息**：不含任何语言字面量、不产诊断。
> 两个消费方：`linter/`（反解析器：按发现节点注册检查器）与 `islands/`（片段模式：
> 发现节点 = 可进管线的语法岛候选，未识别位点 = water）。

## 推导链（逐层单向，无环）

```
parser.setup_grammar（规则表）
   → grammar_slicer.build_slice_tree（规则 → 切片树）
   → first_set.first_tokens（FIRST 集单一实现，nullable 开关两种语义）
   → lookahead.LookaheadTable（token → 候选规则：A 类关键字 / B 类标识符+前缀路径）
   → discovery.Discovery（块/括号栈 + 前瞻 + [discovery] 声明 → DiscoveredNode 树）
```

语言事实（容器 / 容器延续 / 属性对 / 子句分隔符）来自语言包 `[discovery]` 声明
（ADR-0025：声明而非猜；未声明 = 空集，引擎不推导猜测）。

## 文件

| 文件 | 一句话 |
|------|--------|
| `node.py` | `DiscoveredNode`（rule/start/end/context/children）、`CTX_TOP`、`UnrecognizedSite`（中立位点，消费方自行转诊断或 water） |
| `grammar_slicer.py` | `build_slice_tree`：GrammarRule → feature 树（块规则取内容部分） |
| `first_set.py` | FIRST 集单一实现：`nullable=False` 强制起始（前缀判别）/ `True` 可能起始（候选筛选） |
| `lookahead.py` | 动态两级前瞻消歧表：A 类 keyword_map / B 类 ident 候选 + 变长前瞻 + 试解析兜底 |
| `discovery.py` | 发现器：token 流 → `DiscoveredNode` 树 + 未识别位点；块/括号栈、结束符推导（`_stmt_ends`）、深度防御 |
| `discovery_shape.py` | `[discovery]` 声明装载与 `is_stmt_container` 单一口径（ADR-0025） |

## 消费方约定

- `linter/`：`LinterScanner` 构造时 `setup_grammar` → `build_slice_tree`，发现后用
  `unrecognized_sites()` 转 `phase-unrecognized` 诊断；检查器/诊断类型留在 linter。
- `islands/`（片段模式）：发现树即分片候选；未被任何节点覆盖或含宏/指令行的区间为
  water，原样保留；岛是否可处理由"过真实管线 + 后验"判定。
- **本层不得 import `linter/`**（依赖方向单向：linter / islands → structure）。

Doc: `structure/README.md`；发现策略细节见模块 docstring；语言事实声明示例
`grammar/verilog/base/_discovery.toml`。
