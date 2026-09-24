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
| `gen_activity` | `file` | `gen_activity` | `gen_activity` | `{文件路径: {id(节点): bool}}`——节点是否落在**选中**的 generate 互斥分支内；`depends_on = ["param_default"]` |

两项都**不声明定位**（`param_default` 的值分散在头部字段与体内声明两种形态；
`gen_activity` 直接以文件根为输入）→ 求解器收到 `hits = [原子根]`，自行走子树。

## 依赖通道（插件内部，不经引擎）

`gen_activity` 的条件求值需要单元常量表 → 声明 `depends_on = ["param_default"]`，
求解器经 `ctx.products["param_default"]` **直接读**前一项产物。引擎只保证拓扑序，
不中转数据（`unit_constants` 角色位随之退场）。

## 引擎角色位 `gen_activity`（过渡，会退场）

容器条目名由插件定 ⇒ 引擎无法按名寻址**自己也要用**的产物。`role` 是引擎能认的**封闭
枚举**，现役只有 `gen_activity`（引擎侧消费方 = `SignalGraphBuilder` 的驱动过滤）。

⚠ **角色位一律是过渡面**：终态（ADR-0019 决策 1）下引擎不消费任何插件产物，故 P3 收口
时 `analyzer/elaboration/contract.py::ROLES` 应为空——这是"重构完成"的可机械检查判据。

## 消费方

引擎把容器注入 `context.extra[CTX_ELABORATION]`。

| 消费方 | 读什么 | 用途 |
|---|---|---|
| `checks/width_check` | `param_default` | 参数化宽度求值（`_params` 表） |
| `checks/hier_check` | `param_default` | 层次成员宽度求值 |
| `checks/latch_check` | `param_default` | 参数化条件判定 |
| `checks/inst_check` | `param_default` | W103（覆盖不存在的参数）——只要**参数名集合** |
| 引擎 `SignalGraphBuilder` | `gen_activity`（经**角色位**） | 层 3 驱动过滤：未选中 generate 分支的驱动不计 |

## 搬迁纪律

`gen_activity` 是引擎侧 `GenerateEvaluator` + `_GenFace` + 文本常量求值链的**逐字搬迁**
（搬迁期与旧实现做过**逐节点对拍**）。⚠ 它仍是**文本模式**求值（先经服务句柄渲染条件
子树再解析文本）——AST-first 改写是**独立改进项**（TODO「文本模式求值/判断（应
AST-first）」），需自己的一套验证，别在搬迁里顺手改。
