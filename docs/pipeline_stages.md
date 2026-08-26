# 管线阶段契约（Pipeline Stages）

> 各阶段**内部**机制见子系统架构文档（linter_architecture / renderer_architecture /
> semantic_checks / component_protocol）；本文档只描述**层间边界**——每个阶段的
> 输入/输出数据形态、阻断语义、跨阶段数据通道。改管线时先看这里，再进子系统。
>
> 更新：2026-08-26（ADR-0007：analyze/transform 改为 schedule 编排的 pass，
> 见 `decisions/0007-pipeline-schedule.md`）

## 阶段序列（run_pipeline_on_source）

```
source(str)
  → macro scan / expand     预处理器（宏展开/条件块占位）
  → lex                     token 流（list[Token]）
  → prescan                 预扫描（顶层声明符号，parser 提示）
  → lint                    前置 token 级 lint（反向解析器，同语法 TOML）
  → parse                   递归下降+回溯+Pratt → AST（Node 树）
  → normalize               规范化（消除 optional/repeat/seq 包装）
  → schedule                编排调度（ADR-0007）：pass 序列，统一锚定在
                            归一化后；缺省 [analyze, transform]，语言包可声明
                            [[pipeline.schedule]] 自由排序/多轮/check pass
  → render                  Doc IR → 文本（含注释回插）
  → format（可选）           formatter 插件（世界 B pass 管线）
```

schedule 内的 pass：kind=analyze 跑一轮 AnalysisTraversal（覆盖 scope）；
kind=transform 跑一轮 AstTransformer（消费 scope）；kind=check 执行插件
handler（`fn(state)`，检查/验证/外部工具挂载）。时点由序列器分配（order
钉号 / after 推导 / 声明序填空），时点冲突 fail-fast。编排器（声明处理 +
排序 + `_run_schedule` 执行）在 `schedule.py` 一个文件闭环，schedules /
mapping_cfg 由管线按 rules_dir 缓存后注入。开关映射：
`analyzer_enabled`/`transform_enabled` 按 kind 过滤；`expand_enhanced=False`
跳过整个调度；`stage` 按 pass 名截断。

## 阻断语义（哪个阶段失败会停管线）

| 阶段 | 阻断条件 | 结果 |
|------|---------|------|
| lint | 语法诊断存在（lint gate） | 停（`no_lint=True` 是显式逃生门） |
| parse | `_parse_truncated`（未消费 token） | 停（部分 AST 不继续渲染——防静默错乱） |
| analyze pass | error 级语义诊断 | 停调度停管线（warning 级继续） |

## 跨阶段数据通道（不是参数，是对象/属性契约）

| 通道 | 生产者 → 消费者 | 契约 |
|------|----------------|------|
| 下划线属性 | parser → analyzer/transform/renderer | `_` 前缀属性穿过 normalizer（`attr_name.startswith("_")` continue）；`Node.dump` 过滤下划线 |
| 注释锚点 | parser `_comment_anchors`/`_line_comment_anchors` → render 回插 | 列表结构内被 production skip 吞掉的注释，渲染后按锚点窗口回插（±3 行启发式） |
| 注释 attachment | parser `_attached_comments` → renderer line_suffix | 行尾注释挂节点，Doc 一等公民渲染（与锚点回插双轨，restore 去重） |
| 变换回调 | analyzer `_ref_callbacks` → transform | 插件收集的回调表（typed_ports 等），transform 期消费 |
| root_scope | analyzer → transform | 语义作用域根（transform 需 scope 非 None 才运行） |
| 宏 marker | preprocessor → render | `// <tpc:macro:N>` 标记残留于 clean_source，render 时还原 |

## 分层原则

- **语言知识不进代码**：阶段行为由 grammar TOML 配置驱动（规则名/token/布局意图）；
  阶段间不传递语言具体假设（如"分号是句子结束符"——由 production 推导）。
- **契约即门禁**：改跨阶段通道时同步更新本文档 + MODEL_INDEX（知识单元 → 文档 →
  实现 → 验证）；下划线属性契约有测试锁定（normalizer 穿过 + Node.dump 过滤）。

## 相关文档

- 各阶段内部：`linter_architecture.md`（lint）、`semantic_checks.md`（analyze）、
  `renderer_architecture.md`（render + 双世界）、`component_protocol.md`（插件协议）
- 数据通道测试：`tests/engine/parser/test_comment_attachment.py`、
  `tests/engine/renderer/`（原语/保真度）
