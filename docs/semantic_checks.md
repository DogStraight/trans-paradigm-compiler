# 语义检查插槽架构（semantic checks）

> 决策依据：`decisions/0004-semantic-check-slot.md`（为什么）。本文件是"怎么拼"。
> 前置调研：`references/static_checkers_survey.md`。
> 状态：设计定稿，实现分阶段进行（见文末计划）。

## 1. 定位与边界

analyzer 阶段（符号表已建立）的语义检查插槽。**只做三件事**：

1. **配置敏感类检查**——tpc 独有：宽度/参数是配置化的，检查"字面量 vs 符号量"的脆弱匹配。
2. **链级溯源**——HDL 领域空白：报告带赋值链（CodeQL path-problem 式）。
3. **声明式规则机制**——用户"配置优先、脚本兜底"的自定义层。

**不做**（Verilator 已覆盖，不重造）：宽度截断/未连接/未使用/锁存器/case 完整性等。

## 2. 架构总览

```
analyzer 遍历（原语按 [RuleName.analyzer] 触发）       ← 已有（check_name_call 范式）
   │
   ├─ L1 声明层：TOML [[checks]] 规则（规则=数据）       ← 新增
   ├─ L2 脚本层：@register 原语 / handler 模块          ← 已有机制 + 元数据
   │
   └─ post-pass 钩子（遍历收集 → 结束后链式走查）        ← 新增（机制核心）
          │
          └─ 统一报告管道（Diagnostic + related 链）     ← 已有 Diagnostic + 链字段
```

## 3. 规则声明 schema（L1+L2 合一）

```toml
# grammar/verilog/plugins/width_check/rules/width_literal.toml
[[checks]]
id = "WC001"
category = "width"          # 类别前缀 = 分类（clang-tidy/Ruff 共识）
severity = "warning"        # error / warning / info
scope = ["rtl", "tb"]       # 作用域（rtl/tb/模块名/文件 glob，后续细化）
message = "literal {size}'h{value} feeds parameterized port {port} (width {width_expr}); use symbolic width"
handler = "_width_check.py:check_width_literal"   # L2 脚本实现；纯声明式规则可缺省，靠 pattern 匹配
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | 全局唯一（前缀=分类，如 WC=width check） |
| `category` | str | 分类：width / naming / race / cdc / style… |
| `severity` | enum | error / warning / info |
| `scope` | list | 适用作用域；与用户配置 per_file 叠加 |
| `message` | str | 模板，`{var}` 插值（对应 ESLint meta.messages / Semgrep $VAR） |
| `handler` | str | 脚本层实现引用 `模块:函数`；缺省 = 纯声明式（后期支持 pattern 字段） |

## 4. 用户配置层（`tpc.toml [checks]`）

```toml
[checks]
enabled   = ["WC001", "W002"]          # 未列出 = 关闭（Semgrep"不选即关"）
overrides = { WC001 = { severity = "error" } }   # severity 提升（ESLint off/warn/error 式）
per_file  = { "tb/**" = { disabled = ["WC001"] } }  # 测试台豁免（Ruff per-file-ignores 式）
```

- 诚实边界：测试台死值是**故意的**（测固定宽度），默认 TB 豁免由用户配置决定，不内置假设。
- 配置加载沿用 fail-fast（ADR-0003）：非法规则 id / severity 直接报错，不静默降级。

## 5. post-pass 钩子协议（机制核心）

现有原语节点锚定，链式检查需要跨节点分析。协议：

```toml
# 插件 tpc.toml
[analyzer]
primitives = ["collect_width_src"]     # 遍历期收集（节点锚定，L2 原语）
postpasses = ["_chain_walk.py:run"]    # 遍历后走查（新机制）
```

```python
# _chain_walk.py
def run(analyzer, context, config) -> None:
    """遍历结束后调用：访问 analyzer.all_symbols / context.extra 中已收集的
    端口、赋值链；沿链走查，向 context.report 报带 related 的诊断。"""
    ...
```

- 实现位置：`analyzer/traversal.py`——`analyze()` 的 `_walk()` 之后、`_resolve_pending()` 附近，新增 postpass 阶段。
- 收集阶段沿用现有原语副作用模式（`context.extra` 传递临时状态，原语不持全局状态——见 `analyzer/context.py` 设计约定）。
- 这是现有 `_resolve_pending`（遍历后统一核对）模式的通用化，机制已验证。

## 6. 符号宽度表示（width 检查基础）

```python
@dataclass
class WidthExpr:
    kind: str          # "literal" | "parameterized" | "derived"
    expr: str          # 原文："16" / "DATA_W" / "DATA_W-1"
    node: Node         # 来源 AST 节点（定位用）
    provenance: str    # 来源：port_decl / assign / concat ...
```

- typed_ports 已带 `packed_range` 一路到 AST，宽度信息现成，`WidthExpr` 在其上抽象。
- 检查规则：`literal` 喂给 `parameterized` 端口 → 可疑（"死值"模式）；`literal` 喂给 `literal` → 正常。

## 7. 链追溯报告（Diagnostic.related）

```python
# analyzer/diagnostic.py 扩展
class Diagnostic:
    ...
    related: list[dict]   # LSP relatedInformation: [{location, message}]
```

报告形态：

```
WC001 warning: literal 16'hFFFF feeds parameterized port DATA_OUT (width DATA_W)
  chain: tb/tb_spi.sv:42  assign spi_data = test_word;      ← 常量源头（related[0]）
         tb/tb_spi.sv:45  spi_if.data = spi_data;            ← 中间（related[1]）
         rtl/spi_io.sv:10 input [DATA_W-1:0] DATA_OUT         ← 参数化端口（主位置）
```

- 与 linter 侧 `LintDiagnostic` 的关系：语义检查走 analyzer 的 `Diagnostic` 通道（符号级）；两通道在 CLI/report 出口统一渲染（后续）。

## 8. 统一抑制语法

```
// tpc-disable[WC001]             行内忽略指定规则
// tpc-disable-next-line WC001    下一行忽略
// tpc-disable                     本行全部
// tpc-disable-file WC001         文件级
```

- 声明层与脚本层规则**自动获得**同一套豁免（解析发生在报告出口，不区分规则来源）。
- 注释 token 由 preprocessor/lexer 现有注释识别承接。

## 9. 测试框架（按层）

- **L1 声明层**：注释驱动测试（Semgrep 式）——样例源文件内 `// ruleid: WC001`（必须命中）/ `// ok: WC001`（不得命中），引擎断言命中集合，零代码。
- **L2 脚本层**：RuleTester 式断言——valid/invalid 用例 + 期望诊断逐字段断言（messageId/level/位置/related 链）。

## 10. 分阶段落地计划

| 阶段 | 内容 | 验证 |
|---|---|---|
| P1 | 机制层：post-pass 钩子 + `Diagnostic.related` + 统一抑制 | 单测（钩子/序列化/抑制解析） |
| P2 | `width_check` 插件窄版：参数化端口 + 字面量 + 单链 | 复现用例：改端口位宽 → 抓到链上死值 |
| P3 | L1 声明式 schema + 注释驱动测试框架 | WC001 迁到声明层，测试全绿 |
| P4 | 用户配置层 `[checks]` + per_file 豁免 | e2e |

> Impl: 待实现（P1 起）——预计落点：`analyzer/traversal.py`（postpass 阶段）、`analyzer/diagnostic.py`（related）、`analyzer/primitives/`（收集原语）、`grammar/verilog/plugins/width_check/`（实例）、`core/plugin_loader.py`（postpasses 声明解析）
> Test: 待实现——`tests/` 随各阶段新增（P2 验收用例：端口位宽变更链上死值）
