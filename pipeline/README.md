# pipeline — 管线编排

> 各阶段（lexer→…→renderer）的编排入口，层间数据形态/阻断语义见
> `docs/pipeline_stages.md`；analyze/transform 的 pass 时点编排见 `schedule.py`
> + `docs/pipeline_stages.md`（编排调度）。

| 文件 | 一句话 |
|------|--------|
| `__init__.py` | 管线编排（`run_pipeline_on_source`，阶段序列化执行） |
| `schedule.py` | 编排调度：pass 声明 + 时点序列器 + 调度构建 |
| `units.py` | 加工单元实例 + 统一时点生成（`[pipeline.units.*]` 声明 → 单元序列） |
| `report_html.py` | 时点轨迹 HTML 报告（`tpc trace --html`，与 check 报告同一视觉语言） |

## 加工单元（units）

`[pipeline.units.<name>]` 显式声明加工单元实例（`type` / `impl` / `after`|`order` /
`params`），时点由调度器统一生成（与 pass 级同构：钉号 → 声明序填空 → `after`
迭代至不动点；冲突 / 环 / 未知引用 → fail-fast）。有声明时**替代**默认 pass 序列。

`impl` 三形态（`units.py::classify_impl`）：

| 形态 | 例 | 执行 |
|------|-----|------|
| 内置执行器 | `builtin.analyze` / `builtin.transform` | 跑整段分析 / 全部插件（粗粒度） |
| 处理器引用 | `mypass.py:fn` | 加载时解析的 handler（check 类） |
| 插件限定名 | `SemanticMappingPlugin` / `slot_runner` | 该单元**只跑该插件**（插件级，5b-3a） |

另一类是**槽位级单元**（5b-3c-3）：用 `slot` 字段声明（与 `impl` 互斥），只跑该槽位
（引擎 `slot_runner` 单槽位执行）——槽位各自独立时点：

```toml
[[pipeline.units.analyze]]
type = "analyze"
impl = "builtin.analyze"

[[pipeline.units.wrapper]]
type = "transform"
slot = "build_wrapper"          # [[transform.slots]] 里声明的槽位名
after = "analyze"
```

序列限定：`analyze` 至多 1；`transform` 要么单个 `builtin.transform`，要么全为
插件/槽位单元（混用会重复执行 → fail-fast）；`check` 不限（可多实例）。
**槽位单元的契约**沿用承担它的插件（`slot_runner`：`requires=["scope"]` / `produces=["slot_transforms"]`）。

**实例化参数（`params`，5b-3b）**：插件单元可用 `params`（表）覆写插件**构造器
关键字参数**（执行层 `cls(**params)`）——同一插件可在多个单元注册为不同实例
（各自参数与时点），如 `SemanticMappingPlugin` 的 `raw_config` 覆写；与构造器
签名不匹配 → 加载期 fail-fast（报签名错误）。槽位 / 内置执行器 / handler 单元
无实例化参数，声明 `params` 即 fail-fast。参数随单元进 trace 条目（可视化）。

### 契约校验（时点边界）

每个单元执行前校验其 `requires` 是否已被满足（初始集 ∪ 前面单元 `produces`），
未满足 → fail-fast 并列出缺失名与当前可用集；通过后并入其 `produces`。
来源：插件单元取**插件注册时的声明**（`register_plugin(produces=..., requires=...)`，
见 `transform/README.md`）；内置执行器取 `_BUILTIN_UNIT_CONTRACTS`。
**无声明 = 不校验**（可选能力）；插件不管时点，时点只在本节配置里编排。

### 时点轨迹报告（可视化产物）

`tpc trace FILE [--html OUT] [--json OUT]`：跑完整管线后取 `ctx.result["trace"]`
，默认打印文本摘要；`--html` 落单文件 HTML（内联 CSS、零依赖），
与 `tpc check --html` 同一视觉语言（共享 `analyzer/report_html.REPORT_CSS`）。

页面内容 = 每单元一张卡片（时点 `#index` / `name` / `kind` 徽标 / `impl` /
黑板新增键） + **artifacts**（插件 `describe()` 自述的自由结构：`slot_runner`
的槽位调用计数、`SemanticMappingPlugin` 的映射表行数与**行来源链**，如
`spi.slave > invert(spi.master) > #miso`）。渲染器只做**通用值树渲染**
（dict → 表格 / list-of-dict → 带表头表格 / 深层 dict → 紧凑缩进行），
不认识任何具体键名——不引入插件/语言知识（同 TOML 规则姿态）。
