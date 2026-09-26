# 渲染器架构：世界 A Doc IR（Renderer Architecture — World A）

> **本文档是渲染器世界 A 的权威说明**——新 session 接手 `renderer/` 改动前必读。
> 双世界：世界 A（本目录，Doc IR 声明式）→ 本文档；世界 B（Verilog formatter
> 文本行 pass 管线，`grammar/verilog/plugins/formatter/`）→
> `grammar/verilog/plugins/formatter/README.md`（2026-09-04 由原 docs 双世界
> 合版拆分，两文档互相指针）。
> 决策背景：改进路线（原 ADR-0006，六阶段）已全部落地——2026-09-04 ADR 收敛
> 删除，决策历史 git log 可追溯；本文档描述世界 A 落地后的实际工作机制与剩余边界。
>
> 更新时间：2026-08-25（ADR-0006 六阶段 + 注释 attachment 完成）；2026-09-04
> （注释单机制同步，见下）。

## 一句话定位（世界 A）

世界 A（本目录 `renderer/`）：AST + 布局 TOML → **Doc IR**（Wadler-Lindig 漂亮
打印机）→ 文本。yaml/c4/verilog 的 `renderer` 布局配置走这条路。

> 双世界关系：世界 B（Verilog formatter pass 管线）见
> `grammar/verilog/plugins/formatter/README.md`。两世界共享验证门禁（real
> 保真度 / vs Verible 差分 / 幂等），但**原语集与布局模型互不相通**——世界 A
> 是 Doc IR 声明式，世界 B 是命令式行 pass。

---

## 世界 A：Doc IR 渲染器（renderer/）

### 数据流

```
AST (parse/normalize 后)
  → Renderer.render(node)
    → normalize_ast（语法层结构保留，下划线元数据穿过）
    → render_node / render_inline（head/body/tail 三段式）
      → eval_expr（TOML 布局表达式 → Doc 原语）
    → layout(doc, max_width)  （Doc IR → 文本）
  → fidelity 后处理（keep_blank 空行回插，可选）
```

### Doc IR 原语（renderer/doc.py）

| 原语 | 语义 |
|------|------|
| `Text` / `Empty` | 字面量 / 空 |
| `Line`（软换行） | flat → 空格；broken → 换行+缩进 |
| `LineBreak`（条件换行） | flat → 消失；broken → 换行+缩进 |
| `Break`（硬换行） | 恒换行+缩进（不强制所在组） |
| `HardBreak`（强制断行） | 恒换行+缩进，**且强制所在组断开**（向上传播） |
| `Concat` | 顺序拼接 |
| `Nest` | 相对缩进偏移（后续行 +N 格） |
| `Align` | 绝对列对齐：后续行缩进列 = `max(当前缩进, N)`（首行不受影响） |
| `Fill` | 流式折行：内容/分隔符交替序列，逐元素贪心放置（中间态折行） |
| `LineSuffix` | 行尾锚定：内容推迟到下一个换行点之前输出（`line_ending=False` 的块注释就地落地） |
| `Union` + `group`/`flatten` | flat/broken 二象性选择 |
| `Prefix` | 首行缩进 + 后续行 Nest 的统一原语 |

**layout 算法**：`best(w, k, doc)` 宽度感知递归。`Union` 分支尝试 flat 版本、
首行超宽则回退 broken（fits 只测第一行，贪心）。`LineSuffix` 在 layout 入口
经 `_resolve_line_suffix` 重写为换行点前的 `Text`（纯函数预处理，内核不动）。

**行尾锚定的推迟范围与两类注释**（2026-09-20 修）：挂起后缀**跨嵌套 Concat/
Nest/Align/Prefix 上提**（Prettier lineSuffix 是全局缓冲，不是按层就地文本化）——
内层原子节点（`Number`/`SelectExpr`）的 doc 常无尾换行点，就地落地会把父级
同行后续内容（语句 `;`、`join` 的 `,`/`)`）印在注释之后 → **落进注释里被吃掉**
（`assign a = v[0] // c` + 换行 + `;` → `assign a = v[0] // c;`：分号消失）。
判类由语言包声明 `Renderer.comment_ends_line` 写入 `LineSuffix.line_ending`：
行终止型（`//`）参与上提；块注释（`/* */`）就地落地（`a /* c */ + b` 不被搬到
行尾）。上提后无换行点可落时（doc/序列结束）追加在末尾（末尾即行尾）。

**换行三态与强制传播**（2026-09-17）：配置侧三态 = `{ soft }`→`Line` /
`{ break }`→`LineBreak`（组断开时在此断）/ `{ hard_break }`→`HardBreak`
（恒断且强制所在组断开）。两条配套规则：
- `group()` 见 `HardBreak` 时**不生成 Union**（直接返回 broken 形态），且节点保留
  在 doc 里 → 嵌套外层同样被强制（Prettier `propagateBreaks` 的构造期实现）；
- layout 入口 `_drop_break_after_hardbreak`：`HardBreak` 之后紧邻的**条件断**
  （`LineBreak`）不再产生新行（已断过，叠加会多出空行）；软断与硬断不动
  （`tail_break` 用连续 `Break` 表达空行）。

### 布局原语（renderer/primitives/，TOML 可声明）

15 个注册原语：`text/ref/join/group/line/indent/opt/soft/break/hard_break/align/
fill/line_suffix/intent/suffix_when`。注册机制：`@register(key)` 装饰器 → 全局调度表 →
`eval_expr` 按 key 分派（`line` 数组元素由 `eval_line` 内联消费，不走分派）。

**suffix_when 值条件后缀**（2026-08-28）：节点属性值满足条件（startswith）时
追加后缀文本，条件不命中返回 None（line 原语跳过）。典型用途：转义标识符
空白终止（IEEE A.9.3，`\\$_BUF_ (` 而非 `\\$_BUF_(`）。引擎零语言知识：
条件与后缀都是布局 TOML 数据。

**intent 意图层**（阶段 4a）：语言包声明"结构 → 布局意图"，引擎推导 Doc，
消灭手拼。词表：`compact`（紧凑列表 = join+first_soft+nest 别名）/ `wrap`
（流式折行 = fill）/ `align`（对齐）/ `anchor`（行尾锚定 = line_suffix）。

**intent 语言包落地**（2026-08-25 批量迁移）：verilog + c4 共 12 处
`join` 列表布局迁移为 `intent = "compact"`（ParameterList/PortList/
TaskPortList/ArgumentList/DeclaratorList/ParamOverrideList/NamedPortList/
SensitivityList/ConcatExpr/CaseItem/AttrSpecList/TypeParamList）。迁移
等价性由全量测试 + e2e ref 对比锁定（877 pytest 全绿）。保留的 join
形态（语义非列表）：`join = "\n"` 块级连接、`no_soft` 硬拼接、
`join = ""` 拼接、token 定义误匹配。

### 布局 TOML 配置形态

每个规则可声明 `[Rule.renderer]`：

```toml
[Rule.renderer.layout]   # head：表达式（str 或原语 dict）
[Rule.renderer.body]     # body：source/items + indent（true=1级/false=0/int=N）
[Rule.renderer.tail]     # tail：text/expr + tail_break（尾部空行数）
[Rule.renderer.override] # 子节点布局覆盖（父→子合并）
```

布局表达式是**声明式**的（原语组合），语言知识全部在 TOML，引擎零硬编码。

### 缩进统一模型（阶段 1）

- 缩进来源归一为 `Renderer._indent(level)` 唯一换算点（`level × _INDENT_STR`）。
- 幽灵 indent 参数已清零：`render_node/eval_expr/各原语 handler` 协议签名
  不再传递无效 indent。
- `body_cfg["indent"]` 与 expr `{indent: N}` 均以 `_INDENT_STR` 为单位。

### 注释处理（单机制，2026-09-04 注释单机制落地）

注释单机制（原 ADR-0013/0014，已收敛删除）确立：普通注释**必须进树**
（Comment 节点 / 节点 `_comment_slots`），渲染端 restore 已纯 tpc marker
通道——锚点回插作为普通注释通道已删除（原"双轨"描述作废）。形态：

- **独立行注释 = Comment 节点**：`collect_line_comments` + 容器项间/首元素
  前独占注释上浮（`_claim_head_comments`）→ join 拆独立行段渲染。
  ⚠ **取用端沿项"首脊线"下钻**（`join._hoist_head_comments`）：首注释由 claim
  领到的是行首规则的**最内层**节点（列表项以标识符开头时是项内的 `Identifier`，
  如 `Enumerator` → `Identifier`），只认项自身 `sub_node` 首位会漏掉它（静默丢
  注释）；分段节点（head/body/tail）不钻，首注释归 body 段渲染。
  另：硬拼列表（`join=""`）的首注释必须补 Break——否则注释粘在前一片段之后，
  `//` 注释会吞掉后续片段（输出非法 C）。
- **行内/行尾 = 节点 `_comment_slots`**：`trailing`（node_renderer →
  LineSuffix 行尾；行终止型推迟、块注释就地，见上文「行尾锚定的推迟范围
  与两类注释」）/ `inline_after`（line.py 遇锚元素插后删槽，join 消费
  锚=分隔符条目）/ `inline`（节点文本前同行前置，行中注释落在 `inline = true`
  规则上时用它——槽位随内联展开迁到替身节点）/ `leading`（node_renderer 前置，
  行尾型：注释紧跟上一片段同行）/ `leading_own_line`（node_renderer 前置，独占
  行型：块首尾各一硬换行、注释间单换行——源中注释自成一行时用它，否则行注释会
  吃掉同行后续内容；行终止型由声明驱动 `Renderer.comment_ends_line` 判定）。
  前置三槽（`leading`/`leading_own_line`/`inline`）统一由 `_leading_slot_docs`
  按源序补出，布局路径与 verbatim 直出路径同源（后者若漏，附着注释连同 marker
  承载的原文一起丢）。
- **pratt 表达式内注释（三分类）**：operator 间隙/表达式入口按“注释前同行
  有无代码 + 注释后同行有无代码”归位——行中 → `_mount_op_comments` 挂
  BinaryOp/TernaryOp/UnaryOp `inline_after[op]`；行尾 → 后续操作数
  `leading`；独占行 → 后续操作数 `leading_own_line`（块首独立成行，源断行
  位置在此；靠锚点插值会在折叠区里定位漂移）。
- 机制细节与测试门禁见 `docs/MODEL_INDEX.md`「注释单机制设计」知识单元。

### 保真度分级（阶段 5）

- `fidelity` 管线参数：`full`（完全重排，默认）/ `keep_blank`（保留空行）。
- `keep_blank`：src→out LCS 匹配映射表，空行完全以源为准——结构重排后源
  相邻结构间的空行在输出对应位置回插，不叠加 renderer 自产空行。
- CLI：`tpc format --fidelity keep_blank`。

---

## 世界 B：见 formatter 插件 README

> 渲染世界 B（Verilog formatter 文本行 pass 管线）已拆分就近
> `grammar/verilog/plugins/formatter/README.md`（2026-09-04，原 docs 双世界
> 合版拆分）——数据流 / 引擎内建遍 / 带结构行 / 边界扫描 / 世界 B 边界与
> 验证见该 README。

## 功能缺口评估（世界 A，对照 ADR-0006 五条边界）

ADR-0006 边界分析提出的五条理论边界，世界 A 相关四条落地后的状态
（B5 世界 B 行上下文已随世界 B 拆分到 formatter README）：

| 边界 | 状态 | 说明 |
|------|------|------|
| B1 缩进无统一模型 | ✅ 已解决 | `_indent()` 唯一换算点 + 幽灵参数清零 |
| B2 group 二元全局表达不了对齐 | 🔶 部分解决 | 新增 `Align`/`Fill` 原语（对齐/中间态折行可表达），但 **layout 的 fits 仍只测第一行、贪心**——全局最优折行（多候选枚举）未实现 |
| B3 注释非一等公民 | ✅ 已解决 | 注释单机制（原 ADR-0013/0014）：普通注释全进树（Comment 节点 / 槽位 / 表达式挂载）；锚点回插仅剩 tpc marker 内部通道（原 ±3 行启发式普通注释路径已删） |
| B4 规范化 vs 保真矛盾 | 🔶 部分解决 | `fidelity=keep_blank` 保留空行，但**仅空行维度**——indent_only 分级缺口：世界 A 无实现，世界 B indent pass 等价能力见 formatter README |

### 仍存在的功能缺口（按可接受性排序）

**可接受（有明确理由/低成本可补）：**

1. **fits 贪心 → 非全局最优**：`Union` 只测第一行宽度，不枚举多候选。这是
   Wadler 原型的标准权衡（O(n) 线性），prettier 同款；对齐/折行已有
   `Align`/`Fill` 原语兜底。**接受**：Doc IR 内核保持简单，复杂折行交给
   世界 B 的惩罚模型。

2. **tpc marker 通道锚点回插**：`inline_comment.py` 现只处理 tpc marker
   内部标记（宏/指令占位还原）——普通注释已全进树（单机制）；marker 通道
   仍锚点窗口回插（内部标记非用户注释，漂移风险低）。marker 以**注释形态**
   穿过管线，标点来自语言包声明（`lexer/comment_syntax.py` +
   `preprocessor/_markers.py`），渲染端不硬编码 `//` / `/* */`。**接受**：real
   保真度门禁（8 module + 关键构造）锁定现状，攻击面在可测范围内。

3. **fidelity 只有空行维度**：`indent_only`（仅缩进）是配置缺口——但世界 B
   的 formatter 已能单独跑 indent pass，等价能力存在。**接受**：管线级
   fidelity 分级留待真实需求驱动。

4. **世界 A/B 原语不互通**：Doc IR 的 align/fill 与世界 B 的 column_align/
   wrap 是两套实现。**接受**：各有取舍——世界 A 声明式（跨语言通用），
   世界 B 命令式（Verilog 高精度，Verible 参照）。统一是"多遍引擎"方向
   （阶段 4b 已铺 PassKind 基础），非当前必须（世界 B 侧见 formatter README）。

**不可接受/需后续关注：**

5. **Layout TOML 无 schema 校验**：布局表达式错误（拼错原语键/类型）静默
   降级为 None，不报错。与 ADR-0003 fail-fast 精神相悖——但布局是渲染
   增强，非配置加载主路径。**后续**：可加布局 schema 校验（P3 声明式
   schema 的落点之一）。

6. **c4/yaml intent 迁移**：c4 ArgumentList 已随 verilog 批量迁移落地
   （023d939，共 12 处）；yaml 布局经实证**无列表 join 形态**——MappingEntry/
   SequenceItem 是固定行（line）+ body 循环、Scalar 是 ref 原子，无 join 列表
   可迁移。**后续**：无（已闭环）。

---

## 验证基线（当前事实，世界 A）

- **877 pytest 全绿**（806 存量 → 877，含 71 个渲染器相关新测试）。
- e2e：real 保真度（PicoRV32 8 module）/ vs Verible 差分 124 例 / 幂等，
  全部通过。
- pyright（renderer + 相关测试）：0 errors。
- 测试分布：`tests/engine/renderer/`（原语/缩进/保真度）、
  `tests/languages/{yaml,c4,verilog}/`（语言包渲染）、`tests/e2e/`（门禁）、
  `tests/engine/parser/test_comment_attachment.py`（attachment）。
- 世界 B（formatter）验证见 `grammar/verilog/plugins/formatter/README.md`。

## 改渲染器前的检查清单

1. 查本文件（世界 A 工作机制）+ `docs/decisions/0006`（为什么）；改世界 B 先查
   `grammar/verilog/plugins/formatter/README.md`。
2. 改世界 A 动 `renderer/`；改世界 B 动 `grammar/verilog/plugins/formatter/`。
3. 新增布局原语：`@register` + 更新 `primitives/__init__.py` 的
   `_PRIMITIVE_MODULES` + 文档本表。
4. 语言知识不进代码：规则名/布局意图一律在 grammar TOML。
5. 验证：对应部件测试 + `tests/e2e/` 门禁 + pyright。
