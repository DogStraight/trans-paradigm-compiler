# ADR-0007: 分析/变换时点配置化与编排管线

- Status: accepted
- Date: 2026-08-26

## 背景

analyze / transform 的**位置、顺序、轮数**此前硬编码在 `run_pipeline_on_source`：
固定序列 parse → normalize → analyze → transform → render，开关只有 boolean
（`analyzer_enabled` / `transform_enabled`）。语言包能配置"做什么"（原语/变换
操作），但配置不了"何时做"、做几轮、按什么顺序。

需求（用户拍板）：
1. 分析和变换的**时点配置化**——统一锚定在归一化后（normalize 之后），
   不做字符级时点（太模糊）。时点 = 数字或序列器按 `after` 推导。
2. 针对时点的**编排管线**——pass 可组合、管线有名字，用户按名称启用
   任意 pass 序列；analyze/transform 自由排序（不强制分析前置）。

## 决策

### 概念模型

- **操作（primitive）**：现有 analyzer 原语 / transform 操作。操作本身
  **不携带时点**——时点是 pass 级概念。
- **pass**：命名的执行单元，kind ∈ {analyze, transform, check}。
  - `analyze` = 跑一轮 `AnalysisTraversal`（复用语言规则），产出/覆盖 scope；
  - `transform` = 跑一轮 `AstTransformer`（消费 scope，None 时跳过）；
  - `check` = 执行插件 handler（`file.py:fn`，签名 `fn(state) -> None`）——
    检查/验证/外部工具挂载，不改 AST。
  - **行为模型可扩展**：后续需要新语义（如自定义后处理）时扩展 kind
    枚举 + `pipeline/__init__.py` 执行分支，不引入泛化类型（曾考虑
    `custom`，无具体消费方且语义未定义，收窄为 `check`）。
- **schedule（编排管线）**：命名的 pass 序列。一个语言包可声明多条，
  调用方按名称选择启用；缺省 `default`。

### 声明（语言包/插件 tpc.toml）

```toml
# 检查 pass（插件声明）
[[pipeline.pass]]
name = "post_check"
kind = "check"
handler = "_check.py:run"

# 编排管线：条目 = 名字（按声明序）或 { name, order | after }
[[pipeline.schedule]]
name = "default"
passes = ["analyze", "transform"]

[[pipeline.schedule]]
name = "transform_first"
passes = [
  { name = "transform", order = 1 },
  { name = "analyze" },
  { name = "post_check", after = "transform" },
]
```

- 内置 pass：`analyze` / `transform`（引擎提供，无声明可用）。同名声明
  冲突 → 报错（fail-fast）。
- 无任何声明时缺省 schedule = `["analyze", "transform"]`（现行为，零变化）。

### 时点序列器（schedule 内）

1. `order = N` 显式钉号；`after = X` 递归推导为 slot(X)+1；无约束条目按
   声明序顺延。
2. 约束冲突即报错：同号（两个条目落同一时点）、after 环、after 引用
   不存在、pass 重名/未知名、check 缺 handler——全部 fail-fast（ADR-0003）。

### 执行与兼容映射

| 现有机制 | 新语义 |
|----------|--------|
| 缺省（无声明） | schedule `default` = [analyze, transform] |
| `analyzer_enabled=False` | 过滤 kind=analyze 的 pass |
| `transform_enabled=False` | 过滤 kind=transform 的 pass |
| `expand_enhanced=False` | 跳过整个 schedule（保留增强语法直渲） |
| `stage="analyze"` | 执行完名为 `analyze` 的 pass 后截断（legacy 值按名匹配） |
| analyze 报 error | 停 schedule 停管线（不变） |

- 多轮执行语义（如两次 transform）是配置方责任，引擎不判幂等。
- 层内时点（analyzer 原语顺序 / transform 插件顺序）不在本决策范围。
- formatter 世界 B（文本层 pass）不合并——层不同。

## 权衡

- 放弃字符级时点（post_parse/pre_render 等）：归一化后是 AST 形态稳定点，
  单一锚点消除"哪个阶段挂哪"的心智负担；代价是失去 parse→normalize 之间的
  注入窗口（当前无消费方）。
- 放弃锚点开放注册：多轮 analyze→transform 用 schedule 表达即可，开放锚点
  注册只会引入第二套排序机制。

## 验证

- 单元：schedule 序列器（order/after/默认序/冲突/环/未知名 fail-fast）。
- e2e：缺省 schedule 与旧行为逐字节一致（全量回归）；transform_first /
  自定义 pass 管线示例。
- 门禁：`tests/engine/pipeline/`（新增）+ 全量 `pytest tests/`。

> Impl: `pipeline/schedule.py`（编排器一体：build_schedules 声明+序列器、
>       `_run_schedule` 执行、pass 执行器 `_run_pass_*`；共享实例
>       schedules/mapping_cfg 由调用方注入）
>       `core/plugin_loader.py::get_pipeline_pass_decls`（收集）
>       `pipeline/__init__.py`（按 rules_dir 缓存后注入编排器）
> Test: `tests/engine/pipeline/test_schedule.py`
