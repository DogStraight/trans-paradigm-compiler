# Gap — formatter（世界 B）行行为边界（宽度折行 / 保留行 / 对齐 / 幂等）

- 状态：混合——设计选择（保留行/宽度折行）接受；**多声明器对齐为实测缺陷
  （2026-09-12，见下节）**；宽度折行残留为摩擦
- 关联：原 `docs/known_limitations.md` Correctness/Engineering 边界（2026-09-04
  按部件拆入本档）；`grammar/verilog/plugins/formatter/README.md`（世界 B 架构）
- 参照：verible-verilog-format / clang-format 的折行与对齐策略

## 边界是什么

1. **折行基于宽度非语义**（接受）：formatter 只在语法安全点折超长行（>100 列，
   惩罚模型，Verible 式）；不做段落实体式重排（不像段落格式化到目标宽）。
2. **保留行结构**（接受）：重新缩进/对齐/折超长，但**永不合并行、不插空行**——
   输出结构源于输入既有行。风格配置编码并经保真基线校验，非硬编码单一 house
   style。
3. **幂等只在保留路径保证**（接受）：展开路径（宏展开/transform）内容按设计
   变化，不幂等检查。
4. **多声明器行的对齐是破坏性的**（**缺陷**；原档"原样保留"描述已过时）：
   P1.5（提交 `aef437e`）实现"多声明拆分对齐"后，`reg [1:0] state, next;` 不再
   原样保留，而是把第二个及之后的声明符推到远处、且**逐行不一致**——真实
   语料实测 226 处命中（ice40 simcells 146 / ice40 cells_sim 46 / picorv32 28 /
   tv80 6）。详见下节「多声明器对齐破坏格式化」。
5. **宽度折行留下部分超长结构不折**（摩擦，**2026-09-12 实测确认**）：无顶层
   安全断点的超长行不折——179 字符单标识符行原样保留；有 `+`/`,` 断点的
   超长行正常折（在 96 列断行）。属可接受空档（输出合法）。

## 为什么是边界（影响面）

- 1/2/3 是刻意设计（保真优先：输出结构跟随输入行，折行只在安全点）——用户
  期望"合并紧凑行"或"语义重排段落"时不满足，但换来源结构稳定 + 可对拍
  （vs Verible 差分门禁）。
- 4/5 中：4 已从"空档"升级为**缺陷**（输出可读性受损，不是"不彻底"）；
  5 仍是空档（无断点超长行不折，但输出合法）。

## 成熟解法参照（见贤思齐）

- clang-format 对声明器列表/超长表达式的折行（`binpack`/`AlwaysBreakAfter`）
  是对齐 4/5 的参照方向（世界 B pass 内，非引擎改动）。
- verible 差分门禁（`tests/differential/run_differential.py`）已是对拍裁判。

## 可实现性（若要改）

- 4：见下节「多声明器对齐破坏格式化」的两条修法（保守回退 / 正确对齐）——
  **动代码前先选路**。
- 5：wrap pass 增加"拼接体无安全断点"的兜底（如逗号/运算符后强制断点）。
- 1/2/3：设计选择，不改（接受；如需段落式重排属新能力，非修复）。
- 验证：`tests/languages/verilog/test_formatter*.py` + vs Verible 差分 + e2e
  幂等门禁。

## 多声明器对齐破坏格式化（2026-09-12 实测）

**最小复现**（`format_source`，默认配置）：

```verilog
module m;
    reg a, b;
    reg ccc, ddd;
endmodule
```

实测输出（第二声明符落列 19 / 21——**不一致**，即不是对齐）：

```
    reg   a,       b;
    reg   ccc,       ddd;
```

**真实语料量化**（`format_source` 跑 `tests/e2e/samples/real/ref/*.v`，匹配
`,\s{4,}<ident>\s*[,;]` 并排除 `$display` 参数行）：

| 语料 | 命中行 |
|---|---|
| ice40 `simcells` | 146 |
| ice40 `cells_sim` | 46 |
| picorv32 | 28 |
| tv80 | 6 |
| darkriscv / serv_top / uart* | 0 |

典型产出（累积漂移，行越拉越长）：

```
    reg  [31:0] reg_pc,             reg_next_pc,             reg_op1, ...
    input       C,             R,             D
```

另经完整管线（`run_pipeline_on_source`）确认：该填充**进入用户可见输出**
（`input clk, rst_n,` → `input        clk,              rst_n,`）。

**根因**：`column_align.py::run_category_pass` 把同一行的多单元
`" ".join(_join_semantic(c, widths) ...)` 拼回一行——非首单元 `indent` 置空，
但 `_join_semantic` 仍为前 3 列补 `width+1` 前缀；该前缀紧跟上一单元文本，
于是名字列位置随上一单元长度漂移（两单元名字等长时才"看起来对齐"）。

**门禁为何没拦住**：

- `tests/languages/verilog/test_column_align.py` 的多声明用例只断言
  `_extract_semantic_multi` 的**提取**结果（名字不丢），不测重组后文本；
- e2e 保真度用 `_strip_all`（抹掉全部空白）比对 → 空白差异天然免疫；
- `.fidelity_cache.json` 只判"保真度不下降"，不是绝对值判据。

**两条修法（选路先于动代码）**：

1. **保守回退**——多声明行不参与对齐（恢复 `_is_multidecl` 跳过语义），
   与 `_extract_semantic` docstring 及本档原描述一致；零风险，代价是回到
   "多声明行不对齐"的已文档化空档。
2. **正确对齐**——重组时按"名字列同基准"计算后缀填充（参照 Verible
   kDataDeclaration 的声明符列对齐）；是新能力，需补形态覆盖测试。

**附带漂移**：`_is_multidecl` docstring 仍写"多声明行直接跳过（保留原文）"，
与 P1.5 之后的行为矛盾（B5 过时注记），修 4 时一并处理。

## 关联条目

- `grammar/verilog/plugins/formatter/README.md`（世界 B：数据流/带结构行/
  引擎内建遍）
- 缺陷引入提交：`aef437e`（P1.5 多声明品类对齐）；实现：
  `grammar/verilog/plugins/formatter/passes/column_align.py::run_category_pass`
- 缺门禁：`tests/languages/verilog/test_column_align.py`（只测提取，不测重组）
- 原 `docs/known_limitations.md`（Correctness line wrapping / preserves /
  idempotence + Engineering column-align / wrap-leaves）
- 差分对拍：`tests/differential/run_differential.py`
