# analyzer/elaboration — 精化协议（引擎侧）

> 定位：**精化协议的代码落点**——引擎只做**文件操作**，"世界由哪些事实构成"归语言包。
> 本包**只提供机制**：项列表与全部语义求解在语言包插件
> （`grammar/<lang>/plugins/elaboration/`，经 `[capabilities] elaborator` 声明）。
> 为什么这样切：引擎若持有端口/参数/信号图/连接这些**语言形状**，就会随语言增删而改
> （verilog 侧曾因此把约 1000 行语言知识放错位置）；把"最小可视单位"压到**文件**，
> 语言知识就只剩插件一处落点（权衡过程见 git log）。

> Impl: analyzer/elaboration/driver.py::Elaborator
> Test: tests/engine/analyzer/test_elaborator_protocol.py

| 文件 | 一句话 |
|------|--------|
| `contract.py` | 契约与**声明解析**：`Locator`（声明式定位：规则名）/ `ElaborationItem`（项）/ `ElaboratorSpec`（能力面）+ `parse_spec` 全字段 fail-fast 校验（未知键 / 重名 / 容器键跨项重复 / `depends_on` 自引用与成环 / `locator` 与 `locator_fn` 二选一） |
| `driver.py` | **驱动器**（引擎侧唯一执行体，语言无关）：按拓扑序驱动「原子枚举 → 定位 → 求解 → 归位 → 强方向核验」；未声明能力 → 全空降级。含 `Atom`（文件 / 单元 / 工程）/ `AtomSource`（原子供源协议）/ `SolveCtx` / `ElaborationResult` |
| `loader.py` | **读取点**：`load_elaborator_spec(rules_dir)` 按语言包作用域查找能力（与 `preprocessor/macro_policy.py` 同款）；未声明 → `None` = 降级 |

## 契约要点

- **项字段**：`name` / `scope` / `locator`|`locator_fn` / `solver` / `provides` / `depends_on`。
- **求解签名**：`fn(hits, atom, ctx) -> Mapping | None`（`None` = 本原子无此类值，合法）。
- **产物容器**：`context.extra[CTX_ELABORATION] = {容器键: {原子键: 值}}`——引擎定容器，
  插件定条目名与值形状。
- **核验方向**（刻意只做强的那个）：求解器返回未声明的容器键 → fail；**不**因"声明了但
  某原子无产物"报错（按原子出产物，空是常态）。理由见 `contract.py` 模块头。
- **降级**：未声明能力 → 不提取、不递归、不注入容器。

## 接线（已完成）

唯一调用点是 `analyzer/checker.py::ProjectChecker`：构造期 `Elaborator(load_elaborator_spec(...))`，
`_elaborate()` 在发现之后运行项列表，把产物容器注入 `context.extra[CTX_ELABORATION]`，
并注入 `CTX_ANALYZED_FILE`（**文件作用域产物的切片依据**——后处理逐文件跑，
语言包靠它取对本文件的产物）。

引擎**不消费任何产物**：角色的机制已整体退场，产物由语言包内的检查经容器读取；
`pipeline` 不参与（精化是 analyzer 阶段的事）。
