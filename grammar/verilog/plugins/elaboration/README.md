# verilog/plugins/elaboration — verilog 精化项与求解器

> **语言知识在这**：单元是什么、参数在哪、怎么求值，全在本组件。引擎侧
> `analyzer/elaboration/` 只驱动「定位 → 求解 → 归位 → 核验」，**不认识 Verilog**。
> 契约与定案：`docs/decisions/0019-elaboration-plugin-protocol.md`。

| 文件 | 一句话 |
|------|--------|
| `tpc.toml` | 组件声明：`[capabilities] elaborator = "_elaborator.py:build_elaborator"`（**纯能力组件**：无语法/分析/变换声明，同 `macro_policy` / `formatter`） |
| `_elaborator.py` | `build_elaborator()` 项列表 + 各求解函数（现役 `param_default`） |

## 现役项

| 项 | 作用域 | 角色位 | 容器键 | 内容 |
|---|---|---|---|---|
| `param_default` | `unit` | `unit_constants` | `param_default` | `{单元名: {参数名: 值表达式文本}}`——头部 `#(P=v)` 优先，体内 `parameter P=v;` 补全 |

本项**不声明定位**（值分散在"头部字段"与"体内 `ParamDeclStmt`"两种形态，单条规则名
表达不了）→ 求解器收到 `hits = [原子根]`，自行走子树。

## 引擎角色位 `unit_constants`（过渡，会退场）

`role = unit_constants` 表示"这张表就是单元级常量绑定"。**引擎侧**过渡期消费方 =
`GenerateEvaluator`（生成条件求值需要单元参数表），而 gen 族按 ADR-0019 **P3** 才迁入
协议。gen 族搬迁完成后，该角色**应随之删除**（`analyzer/elaboration/contract.py::ROLES`）
——它是为解决"引擎按插件起的条目名寻址"而设的最小机制，不是长期面。

## 消费方

引擎把容器注入 `context.extra[CTX_ELABORATION]`；搬迁前各自读 `ModuleInfo.params`
的五处，现统一读 `param_default`：

| 消费方 | 用途 |
|---|---|
| `checks/width_check` | 参数化宽度求值（`_params` 表） |
| `checks/hier_check` | 层次成员宽度求值 |
| `checks/latch_check` | 参数化条件判定 |
| `checks/inst_check` | W103（覆盖不存在的参数）——只要**参数名集合** |
| 引擎 `GenerateEvaluator` | 生成条件求值（过渡；经 `role` 取，P3 退场） |
