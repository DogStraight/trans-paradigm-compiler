# pipeline — 管线编排

> 各阶段（lexer→…→renderer）的编排入口，层间数据形态/阻断语义见
> `docs/pipeline_stages.md`；analyze/transform 的 pass 时点编排见 `schedule.py`
> + `docs/pipeline_stages.md`（编排调度）。

| 文件 | 一句话 |
|------|--------|
| `__init__.py` | 管线编排（`run_pipeline_on_source`，阶段序列化执行） |
| `schedule.py` | 编排调度：pass 声明 + 时点序列器 + 调度构建 |
| `units.py` | 加工单元实例 + 统一时点生成（`[pipeline.units.*]` 声明 → 单元序列） |

## 加工单元（units，ADR-0015 §1）

`[pipeline.units.<name>]` 显式声明加工单元实例（`type` / `impl` / `after`|`order` /
`params`），时点由调度器统一生成（与 pass 级同构：钉号 → 声明序填空 → `after`
迭代至不动点；冲突 / 环 / 未知引用 → fail-fast）。有声明时**替代**默认 pass 序列。

`impl` 三形态（`units.py::classify_impl`）：

| 形态 | 例 | 执行 |
|------|-----|------|
| 内置执行器 | `builtin.analyze` / `builtin.transform` | 跑整段分析 / 全部插件（粗粒度） |
| 处理器引用 | `mypass.py:fn` | 加载时解析的 handler（check 类） |
| 插件限定名 | `SemanticMappingPlugin` / `slot_runner` | 该单元**只跑该插件**（插件级，5b-3a） |

序列限定：`analyze` 至多 1；`transform` 要么单个 `builtin.transform`，要么全为
插件单元（混用会重复执行 → fail-fast）；`check` 不限（可多实例）。

### 契约校验（时点边界，ADR-0015 §3）

每个单元执行前校验其 `requires` 是否已被满足（初始集 ∪ 前面单元 `produces`），
未满足 → fail-fast 并列出缺失名与当前可用集；通过后并入其 `produces`。
来源：插件单元取**插件注册时的声明**（`register_plugin(produces=..., requires=...)`，
见 `transform/README.md`）；内置执行器取 `_BUILTIN_UNIT_CONTRACTS`。
**无声明 = 不校验**（可选能力）；插件不管时点，时点只在本节配置里编排。
