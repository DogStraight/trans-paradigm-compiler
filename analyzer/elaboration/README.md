# analyzer/elaboration — 精化协议（引擎侧）

> 定位：ADR-0019 的代码落点——引擎只做**文件操作**，"世界由哪些事实构成"归语言包。
> 本包**只提供机制**：项列表与全部语义求解在语言包插件
> （`grammar/<lang>/plugins/elaboration/`，经 `[capabilities] elaborator` 声明）。
> 定案与权衡：`docs/decisions/0019-elaboration-plugin-protocol.md`。

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

## 未接线状态（P1）

按 ADR-0019 分期，本包当前**只新增不接线**：`ProjectChecker` / `pipeline` 尚不调用
`load_elaborator_spec`，`[structure]` 声明面与 `analyzer/structure.py` 的引擎侧实现
仍在原位。接线自 P2（`param_default` + `param_override`）起，逐族替换并**同批删除**
旧实现（不留双路径）。
