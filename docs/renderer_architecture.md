# 渲染器架构（Renderer Architecture）

> **本文档是渲染器当前状态的权威说明**——新 session 接手渲染器改动前必读。
> 决策背景见 `decisions/0006-renderer-improve-roadmap.md`（ADR-0006，改进路线
> 全部六阶段已落地）；本文档描述落地后的实际工作机制与剩余边界。
>
> 更新时间：2026-08-25（ADR-0006 六阶段 + 注释 attachment 全部完成后）。

## 一句话定位

tpc 的渲染器是**双世界**结构：

- **世界 A**（`renderer/`）：AST + 布局 TOML → **Doc IR**（Wadler-Lindig 漂亮
  打印机）→ 文本。yaml/c4/verilog 的 `renderer` 布局配置走这条路。
- **世界 B**（`grammar/verilog/plugins/formatter/`）：**文本行 pass 管线**，
  操作裸 `list[str]` + 行上下文（LineContext）。verilog 的 `format_source`
  与管线 `format_output` 走这条路（缩进/品类对齐/端口对齐/折行）。

两世界共享验证门禁（real 保真度 / vs Verible 差分 / 幂等），但**原语集与
布局模型互不相通**——世界 A 是 Doc IR 声明式，世界 B 是命令式行 pass。

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
| `Break`（硬换行） | 恒换行+缩进 |
| `LineBreak` | 条件换行（尾部专用，flat 消失） |
| `Concat` | 顺序拼接 |
| `Nest` | 相对缩进偏移（后续行 +N 格） |
| `Align` | 绝对列对齐：后续行缩进列 = `max(当前缩进, N)`（首行不受影响） |
| `Fill` | 流式折行：内容/分隔符交替序列，逐元素贪心放置（中间态折行） |
| `LineSuffix` | 行尾锚定：内容推迟到下一个换行点之前输出 |
| `Union` + `group`/`flatten` | flat/broken 二象性选择 |
| `Prefix` | 首行缩进 + 后续行 Nest 的统一原语 |

**layout 算法**：`best(w, k, doc)` 宽度感知递归。`Union` 分支尝试 flat 版本、
首行超宽则回退 broken（fits 只测第一行，贪心）。`LineSuffix` 在 layout 入口
经 `_resolve_line_suffix` 重写为换行点前的 `Text`（纯函数预处理，内核不动）。

### 布局原语（renderer/primitives/，TOML 可声明）

14 个注册原语：`text/ref/join/group/line/indent/opt/soft/break/align/fill/
line_suffix/intent/suffix_when`。注册机制：`@register(key)` 装饰器 → 全局调度表 →
`eval_expr` 按 key 分派。

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

### 注释处理（双轨）

- **AST 路径**：`collect_line_comments` → Comment 节点 → 原生渲染。
- **锚点路径**（列表结构内被 production skip 吞掉的注释）：parser 收集
  `_comment_anchors`/`_line_comment_anchors` → `inline_comment.py` 渲染后
  字符串级回插（锚点窗口启发式）。
- **attachment 路径**（阶段 4 注释遍）：parser `parse_token` 收集行尾注释
  时挂到节点 `_attached_comments` → renderer 用 `line_suffix` 原语锚定到
  语句行尾（Doc 一等公民）。与锚点回插双轨并存（restore 去重防重复）。

### 保真度分级（阶段 5）

- `fidelity` 管线参数：`full`（完全重排，默认）/ `keep_blank`（保留空行）。
- `keep_blank`：src→out LCS 匹配映射表，空行完全以源为准——结构重排后源
  相邻结构间的空行在输出对应位置回插，不叠加 renderer 自产空行。
- CLI：`tpc format --fidelity keep_blank`。

---

## 世界 B：Verilog formatter 插件（grammar/verilog/plugins/formatter/）

### 数据流

```
源文本
  → split_port_close_lines / split_inst_tail_lines（拆粘连行）
  → BoundaryScanner.scan（token 流 → 每行 LineContext）
  → FormatterEngine.run（按配置依次执行 pass）
    → indent（缩进重排，最前）
    → ifdef（条件编译块内容缩进）
    → category（品类对齐：port_dir/declaration/parameter/...）
    → inst_port（实例端口对齐）
    → wrap（宽度折行，最后）
  → 清理行尾尾随空格
```

### 引擎内建遍（阶段 4b）

- `PassKind` 枚举：indent/ifdef/align/wrap/comment/annotate/custom——pass
  从"自由 handler 函数"升格为"类型化内建遍"。
- `criterion` 量化拒绝准则：`min_group_size`/`max_span`/`max_width`，运行前
  检查、不满足跳过该遍（布局决策显式化，cmake-format 借鉴方向）。
- 实际接入：wrap 带 `max_width` 拒绝、品类对齐带 `min_group_size` 拒绝、
  wrap_comments 升格 COMMENT 遍（均默认关闭或纯优化）。

### 带结构行（阶段 3）

- 拆行 pass（inst_port/wrap）就地同步 contexts：拆出的每段派生复制源行 ctx，
  wrap 续行段标记 `multi_line_cont`——根治"拆行后行号漂移"。
- 引擎 run 后兜底对齐：漏同步的 pass 自动按就近行派生补齐。

### 边界扫描（boundary.py）

token 流单次遍历 → 每行 LineContext：scope 栈/块头块尾/ifdef 分支/单语句头/
多行续行/端口列表结束/指令行。**结构 token 全部从语法规则推导**（`is_block`/
`analyzer.scope.kind`/production 尾关键字终结符），零硬编码语言知识。

---

## 功能缺口评估（对照 ADR-0006 五条边界）

ADR-0006 边界分析提出的五条理论边界，落地后的状态：

| 边界 | 状态 | 说明 |
|------|------|------|
| B1 缩进无统一模型 | ✅ 已解决 | `_indent()` 唯一换算点 + 幽灵参数清零 |
| B2 group 二元全局表达不了对齐 | 🔶 部分解决 | 新增 `Align`/`Fill` 原语（对齐/中间态折行可表达），但 **layout 的 fits 仍只测第一行、贪心**——全局最优折行（多候选枚举）未实现 |
| B3 注释非一等公民 | 🔶 部分解决 | `LineSuffix` + attachment 路径（Doc 一等公民），但**锚点回插仍是字符串级启发式**（±3 行窗口，漂移即丢）——attachment 未完全替换它 |
| B4 规范化 vs 保真矛盾 | 🔶 部分解决 | `fidelity=keep_blank` 保留空行，但**仅空行维度**——verible 的"保留折行/仅缩进"分级未实现（indent_only 是配置缺口） |
| B5 世界 B 行上下文与 AST 分离 | ✅ 已解决 | 带结构行（拆行同步 contexts + 引擎兜底），行号漂移根治 |

### 仍存在的功能缺口（按可接受性排序）

**可接受（有明确理由/低成本可补）：**

1. **fits 贪心 → 非全局最优**：`Union` 只测第一行宽度，不枚举多候选。这是
   Wadler 原型的标准权衡（O(n) 线性），prettier 同款；对齐/折行已有
   `Align`/`Fill` 原语兜底。**接受**：Doc IR 内核保持简单，复杂折行交给
   世界 B 的惩罚模型。

2. **锚点回插仍是启发式**：`inline_comment.py` ±3 行窗口匹配，注释密集时
   可能错位（only_tpc 路径已跳过普通注释规避）。attachment 是前进方向但
   未完全覆盖块结束符注释。**接受**：real 保真度门禁（8 module + 关键构造）
   锁定现状，攻击面在可测范围内。

3. **fidelity 只有空行维度**：`indent_only`（仅缩进）是配置缺口——但世界 B
   的 formatter 已能单独跑 indent pass，等价能力存在。**接受**：管线级
   fidelity 分级留待真实需求驱动。

4. **世界 A/B 原语不互通**：Doc IR 的 align/fill 与世界 B 的 column_align/
   wrap 是两套实现。**接受**：各有取舍——世界 A 声明式（跨语言通用），
   世界 B 命令式（Verilog 高精度，Verible 参照）。统一是"多遍引擎"方向
   （阶段 4b 已铺 PassKind 基础），非当前必须。

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

## 验证基线（当前事实）

- **877 pytest 全绿**（806 存量 → 877，含 71 个渲染器相关新测试）。
- e2e：real 保真度（PicoRV32 8 module）/ vs Verible 差分 124 例 / 幂等，
  全部通过。
- pyright（renderer + formatter + 相关测试）：0 errors。
- 测试分布：`tests/engine/renderer/`（原语/缩进/保真度）、
  `tests/languages/{yaml,c4,verilog}/`（语言包渲染）、`tests/e2e/`（门禁）、
  `tests/engine/parser/test_comment_attachment.py`（attachment）。

## 改渲染器前的检查清单

1. 查本文件（工作机制）+ `decisions/0006`（为什么）。
2. 改世界 A：动 `renderer/`；改世界 B：动 `grammar/verilog/plugins/formatter/`。
3. 新增布局原语：`@register` + 更新 `primitives/__init__.py` 的
   `_PRIMITIVE_MODULES` + 文档本表。
4. 语言知识不进代码：规则名/布局意图一律在 grammar TOML。
5. 验证：对应部件测试 + `tests/e2e/` 门禁 + pyright。
