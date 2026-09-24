# verilog/plugins/elaboration — verilog 精化项与求解器

> **语言知识在这**：单元是什么、参数在哪、怎么求值、generate 怎么判——全在本组件。
> 引擎侧 `analyzer/elaboration/` 只驱动「定位 → 求解 → 归位 → 核验」，**不认识 Verilog**。
> 契约与定案：`docs/decisions/0019-elaboration-plugin-protocol.md`。

| 文件 | 一句话 |
|------|--------|
| `tpc.toml` | 组件声明：`[capabilities] elaborator = "_elaborator.py:build_elaborator"`（**纯能力组件**：无语法/分析/变换声明，同 `macro_policy` / `formatter`） |
| `_elaborator.py` | `build_elaborator()` 项列表 + 各求解函数 |

## 现役项

| 项 | 作用域 | 角色位 | 容器键 | 内容 |
|---|---|---|---|---|
| `param_default` | `unit` | — | `param_default` | `{单元名: {参数名: 值表达式文本}}`——头部 `#(P=v)` 优先，体内 `parameter P=v;` 补全 |
| `port_decls` | `unit` | `unit_ports` | `port_decls` | `{单元名: {端口名: {name, direction, width_expr, net_type, decl_node}}}`——ANSI 头部 / 裸名头部 / 体内旧式声明三形态合并，**头部优先** |
| `connections` | `file` | `unit_connections` | `connections` | `{文件路径: [{inst_name, module_name, inst_node, file, connects, ordered}]}`——命名连接进 `connects`，其余按位置序进 `ordered` |
| `gen_activity` | `file` | `gen_activity` | `gen_activity` | `{文件路径: {id(节点): bool}}`——节点是否落在**选中**的 generate 互斥分支内；`depends_on = ["param_default"]` |

四项都**不声明定位**（值/形态分散在多种节点形态或整个原子，单条规则名表达不了）→
求解器收到 `hits = [原子根]`，自行走子树。

## 依赖通道（插件内部，不经引擎）

`gen_activity` 的条件求值需要单元常量表 → 声明 `depends_on = ["param_default"]`，
求解器经 `ctx.products["param_default"]` **直接读**前一项产物。引擎只保证拓扑序，
不中转数据（`unit_constants` 角色位随之退场）。

## 引擎角色位（过渡，会退场）

容器条目名由插件定 ⇒ 引擎无法按名寻址**自己也要用**的产物。`role` 是引擎能认的**封闭
枚举**：`gen_activity`（引擎侧 `SignalGraphBuilder` 的驱动过滤）、`unit_ports`
（层 2/3 的端口形态；**已登记、引擎尚未切换**）、`unit_connections`（层 2 连接表；
**已登记、引擎尚未切换**）。

⚠ **角色位一律是过渡面**：终态（ADR-0019 决策 1）下引擎不消费任何插件产物，故 P3 收口
时 `analyzer/elaboration/contract.py::ROLES` 应为空——这是"重构完成"的可机械检查判据。
（已核实：文件发现阶段只用**声明**（实例规则名 + 名字字段 + 扩展名 + 关键字）与通用 AST
操作，**不需要插件产物**，故该判据可达。）

## 消费方

引擎把容器注入 `context.extra[CTX_ELABORATION]`。

| 消费方 | 读什么 | 用途 |
|---|---|---|
| `checks/width_check` | `param_default` | 参数化宽度求值（`_params` 表） |
| `checks/hier_check` | `param_default` | 层次成员宽度求值 |
| `checks/latch_check` | `param_default` | 参数化条件判定 |
| `checks/inst_check` | `param_default` | W103（覆盖不存在的参数）——只要**参数名集合** |
| 引擎 `SignalGraphBuilder` | `gen_activity`（经**角色位**） | 层 3 驱动过滤：未选中 generate 分支的驱动不计 |
| 引擎 `ConnectionElaborator` / `SignalGraphBuilder` | `port_decls`（经**角色位**，**P3-②b 起**） | 层 2/3 的端口名/方向/宽度 |
| 引擎 `SignalGraphBuilder` / `ProjectChecker` | `connections`（经**角色位**，**P3-②b 起**） | 层 3 按连接记驱动/负载；注入 `context.extra["connections"]` 供 postpass（W104 等） |

`port_decls` 与 `connections` 目前**只新增、无人消费**（引擎侧 `ModuleInfo.ports` 与
`FileResult.connections` 仍在原位）——本阶段的意义是与引擎产物做**等价性对拍**：
`port_decls` 用两个夹具（ANSI 头部 / 裸名头部 + 体内旧式声明），`connections` 覆盖命名 /
位置 / 命名但值为空（`.a()`）三种连接形态。

> ✅ 搬迁查过一个**时序风险，结论是不存在**：引擎的层 2 是在**发现过程中逐文件**算的，
> 而精化 pass 在**发现之后**统一跑；若层 2 依赖 `module_index`（彼时只填了一部分），两者
> 结果会不同。实测读码：`elaborate_connections` **完全不读端口表**，只读声明字段并把连接
> 表达式渲染成文本 → 无时序风险（对拍即证据）。

## 搬迁纪律

`gen_activity` 是引擎侧 `GenerateEvaluator` + `_GenFace` + 文本常量求值链的**逐字搬迁**
（搬迁期与旧实现做过**逐节点对拍**）。⚠ 它仍是**文本模式**求值（先经服务句柄渲染条件
子树再解析文本）——AST-first 改写是**独立改进项**（TODO「文本模式求值/判断（应
AST-first）」），需自己的一套验证，别在搬迁里顺手改。
