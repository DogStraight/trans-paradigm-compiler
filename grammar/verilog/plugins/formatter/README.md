# formatter/ — 渲染世界 B：Verilog formatter 插件（文本行 pass 管线）

> 双世界：世界 B（本插件——renderer/ 世界 A 输出文本后的文本行 pass 管线）
> → 本文档；世界 A（Doc IR 声明式渲染，`renderer/`）→
> `renderer/renderer_architecture.md`（2026-09-04 由原 docs/renderer_architecture.md
> 双世界合版拆分，两文档互相指针）。
> 决策背景见 `docs/decisions/0006-renderer-improve-roadmap.md`（ADR-0006）。

## 一句话定位

Verilog formatter：**文本行 pass 管线**，操作裸 `list[str]` + 行上下文
（LineContext）。verilog 的 `format_source` 与管线 `format_output` 走这条路
（缩进/品类对齐/端口对齐/折行）。与世界 A 原语集与布局模型互不相通——世界 A
是 Doc IR 声明式，世界 B 是命令式行 pass（各有取舍：A 跨语言通用，B Verilog
高精度，Verible 参照）。

## 数据流

```
源文本
  → split_port_close_lines / split_inst_tail_lines（拆粘连行）
  → BoundaryScanner.scan（token 流 → 每行 LineContext）
  → FormatterEngine.run（按配置依次执行 pass）
    → indent（缩进重排，最前）
    → ifdef（条件编译块内容缩进）
    → category（品类对齐：port_dir/declaration/parameter/...）
    → inst_port（实例端口对齐）
    → wrap（宽度折行，最后）
  → 清理行尾尾随空格
```

## 引擎内建遍（阶段 4b）

- `PassKind` 枚举：indent/ifdef/align/wrap/comment/annotate/custom——pass
  从"自由 handler 函数"升格为"类型化内建遍"。
- `criterion` 量化拒绝准则：`min_group_size`/`max_span`/`max_width`，运行前
  检查、不满足跳过该遍（布局决策显式化，cmake-format 借鉴方向）。
- 实际接入：wrap 带 `max_width` 拒绝、品类对齐带 `min_group_size` 拒绝、
  wrap_comments 升格 COMMENT 遍（均默认关闭或纯优化）。

## 带结构行（阶段 3）

- 拆行 pass（inst_port/wrap）就地同步 contexts：拆出的每段派生复制源行 ctx，
  wrap 续行段标记 `multi_line_cont`——根治"拆行后行号漂移"。
- 引擎 run 后兜底对齐：漏同步的 pass 自动按就近行派生补齐。

## 边界扫描（boundary.py）

token 流单次遍历 → 每行 LineContext：scope 栈/块头块尾/ifdef 分支/单语句头/
多行续行/端口列表结束/指令行。**结构 token 全部从语法规则推导**（`is_block`/
`analyzer.scope.kind`/production 尾关键字终结符），零硬编码语言知识。

## 世界 B 边界（对照 ADR-0006）

| 边界 | 状态 | 说明 |
|------|------|------|
| B4（世界 B 侧）indent_only 缺口 | 🔶 等价能力在 | 管线 fidelity 只有空行维度（世界 A `keep_blank`）；indent_only 分级未做管线级——本插件 indent pass 已能单独跑，等价能力存在，留待真实需求驱动（世界 A 侧见 renderer/renderer_architecture.md B4） |
| B5 世界 B 行上下文与 AST 分离 | ✅ 已解决 | 带结构行（拆行同步 contexts + 引擎兜底），行号漂移根治 |

> 缺口 4（世界 A/B 原语不互通，Doc IR align/fill vs 本插件 column_align/wrap）：
> 两世界各有取舍非必须统一，完整评估见 `renderer/renderer_architecture.md`。

## 文件职责

| 文件 | 职责 |
|------|------|
| `__init__.py` | 插件入口：`format_source` / pass 组装 |
| `engine.py` | 引擎：内建遍编排（`PassKind` + `criterion` 量化拒绝） |
| `boundary.py` | 结构边界扫描（token 流 → 每行 LineContext） |
| `grouping.py` | 格式化行分组工具 |
| `style.py` | formatter 风格参数加载 |
| `passes/` | 内建 pass 族（`indent`/`ifdef`/`ifdef_annotate`/`column_align`/`inst_port`/`wrap`/`wrap_comments`） |
| `_capability.py` | 能力入口（`[capabilities]` 声明，见 `docs/component_protocol.md`） |

## 验证

- `tests/languages/verilog/test_formatter*.py`（pass 行为单测）
- `tests/differential/`（vs verible-verilog-format 对拍，可选依赖）+ e2e 门禁
  （real 保真度 / 幂等，与世界 A 共享）
