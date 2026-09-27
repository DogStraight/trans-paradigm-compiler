# verilog/plugins/elaboration — verilog 精化项与求解器

> **语言知识在这**：单元/实例是什么、参数在哪、怎么求值、端口什么形态、信号谁驱动谁、
> generate 怎么判——全在本组件。引擎侧 `analyzer/elaboration/` 只驱动「定位 → 求解 →
> 归位 → 核验」，**不认识 Verilog**。
> 契约（引擎侧）：`analyzer/elaboration/README.md` + `core/component_protocol.md` §1b。

| 文件 | 一句话 |
|------|--------|
| `tpc.toml` | 组件声明：`[capabilities] elaborator = "_elaborator.py:build_elaborator"`（**纯能力组件**：无语法/分析/变换声明，同 `macro_policy` / `formatter`） |
| `_elaborator.py` | `build_elaborator()` 项列表 + 参数/端口/连接/generate 四项的求解函数 |
| `_graph.py` | 层 3 信号图（`signal_graph` 项，400 行搬迁自引擎 `SignalGraphBuilder`）——分文件是为了不让单文件过大 |

## 现役项（6 项，**均无角色位**——机制已退场）

| 项 | 作用域 | 容器键 | 内容 |
|---|---|---|---|
| `param_default` | `unit` | `param_default` | `{单元名: {参数名: 值表达式文本}}`——头部 `#(P=v)` 优先，体内 `parameter P=v;` 补全 |
| `port_decls` | `unit` | `port_decls` | `{单元名: {端口名: {name, direction, width_expr, net_type, decl_node}}}`——ANSI 头部 / 裸名头部 / 体内旧式声明三形态合并，**头部优先** |
| `connections` | `file` | `connections` | `{文件路径: [{inst_name, module_name, inst_node, file, connects, ordered}]}`——命名连接进 `connects`，其余按位置序进 `ordered` |
| `param_override` | `file` | `param_override` | `{文件路径: [{inst_name, module_name, inst_node, params, changed}]}`——实例化点**覆盖后**的参数表（调用者参数 → 目标默认 → site 覆盖）；`changed` = 覆盖 ≠ 默认 |
| `gen_activity` | `file` | `gen_activity` | `{文件路径: {id(节点): bool}}`——节点是否落在**选中**的 generate 互斥分支内 |
| `signal_graph` | `project` | `signal_graph` | `{(单元名, 信号名): {drivers: [...], loads: [...]}}`——层 3 全工程驱动/负载图（含 output 穿透与实例链路径） |

五项都**不声明定位**（值/形态分散在多种节点形态或整个原子，单条规则名表达不了）→
求解器收到 `hits = [原子根]`（`project` 作用域则为空），自行走子树。

## 依赖通道（插件内部，不经引擎）

```
param_default ──depends_on──▶ gen_activity ──┐
param_default ──depends_on──▶ param_override │
connections ────depends_on──▶ param_override │
                              port_decls ────┼──depends_on──▶ signal_graph
                              connections ───┘
```

声明 `depends_on` 后引擎**只保证拓扑序**，数据由求解器经 `ctx.products[...]` **直接读**
前项产物——引擎不中转、不解释。层 3 一次消费**三个**自身产物（`connections` /
`port_decls` / `gen_activity`），这是依赖通道被用满的地方。

## 引擎角色位：**机制已整体退场**（重构终态）

`role` 曾是"引擎自己要用的产物"的寻址机制（引擎定义的封闭枚举）。**P3 收口后引擎不消费
任何插件产物**（层 2/3 与 generate 求值都在本插件侧，产出方与消费方同源），故该机制
**整体删除**（`role` 字段 / `ROLES` 枚举 / `role_key`）——**不留登记槽**：`ROLES` 为空时
任何 role 声明都必然 fail-fast，字段已不可合法使用，留着只是"不可用的配置面"。
现声明 `role` 会被"未知键"在加载期拦下（响亮失败，不静默忽略）。

历史角色（逐阶段退场）：`unit_constants`（P3-①）、`unit_connections` / `unit_signal_graph`
（P3-②c-1）、`unit_ports` / `gen_activity`（P3-②c-2b）。

## 消费方（全部在语言包内，读产物容器）

引擎把容器注入 `context.extra[CTX_ELABORATION]`；**按文件的产物**用引擎给的
`context.extra[CTX_ANALYZED_FILE]`（当前分析文件）取切片。

| 消费方 | 读什么 | 用途 |
|---|---|---|
| `checks/width_check` | `param_default` + `port_decls` + `param_override` | 参数化宽度求值；端口连接宽度（位置连接按**声明序**匹配端口）；实例化点覆盖后参数表（B3/B4，经 `_shared.override_of`） |
| `checks/hier_check` | `param_default` + `port_decls` | 层次成员/端口宽度 |
| `checks/latch_check` | `param_default` | 参数化条件判定（**不碰端口**） |
| `checks/inst_check` | 四者 | W101/W102/W103/W104/W105/WC001——命名/位置连接、参数名集合、驱动/负载图 |
| 本组件 `_graph.py` | `connections` / `port_decls` / `gen_activity` | 层 3 信号图（插件内部依赖） |

## 搬迁纪律（为什么可以信这五项）

每一项在**删掉引擎侧实现之前**都与它做过**等价性对拍**（含真实语料）：
`param_default`↔`ModuleExtractor._fill_params`、`port_decls`↔`_fill_ports`、
`connections`↔`ConnectionElaborator`、`gen_activity`↔`GenerateEvaluator`（逐节点）、
`signal_graph`↔`SignalGraphBuilder`（逐条目，7 夹具）。删除后对拍退化为**golden 行为守卫
+ 退场守卫**（引擎侧类/属性不得复活）。

> ✅ 搬迁查过一个**时序风险，结论是不存在**：引擎的层 2 原是在**发现过程中逐文件**算的，
> 而精化 pass 在**发现之后**统一跑；若层 2 依赖 `module_index`（彼时只填了一部分），两者
> 结果会不同。实测读码：`elaborate_connections` **完全不读端口表**，只读声明字段并渲染
> 连接表达式 → 无时序风险（对拍即证据）。

⚠ `gen_activity` 仍是**文本模式**求值（先经服务句柄渲染条件子树再解析文本）——AST-first
改写是**独立改进项**（TODO「文本模式求值/判断（应 AST-first）」），动机是插件代码质量而非
"消除渗透"，需自己一套验证，**别在搬迁里顺手改**。
